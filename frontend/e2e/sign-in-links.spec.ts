/**
 * Every link that signs somebody in, against a real GoTrue.
 *
 * The client moved from the implicit flow to PKCE because the implicit flow
 * put the session itself in the URL (`#access_token=…&refresh_token=…`), and
 * Datadog RUM recorded it on every sign-in. These walk each way in through
 * the local Supabase stack `frontend-e2e.yml` boots, and hold two things for
 * all of them: the person ends up signed in, and nothing that could sign
 * anyone in is left in the address bar.
 *
 *   - the link our send-email hook now builds (`/auth/confirm#token_hash=…`),
 *     opened in a browser that never asked for it;
 *   - the same for password recovery, which lands on the new-password form;
 *   - a link mailed before the switch (GoTrue's `/auth/v1/verify`), which
 *     still comes back with a fragment session until it expires;
 *   - a link used twice;
 *   - "Email me a link instead" end to end through Mailpit: the real PKCE
 *     email, followed in the browser that asked (`?code=` exchange) and its
 *     token hash in one that did not.
 *
 * Google cannot be driven here; its `?code=` exchange is the same call the
 * Mailpit case makes, and the unit tests in `lib/__tests__/authLanding.test.ts`
 * cover its URL handling.
 */
import { test, expect, type APIRequestContext, type Page } from "@playwright/test";

const SUPABASE_URL = process.env.SUPABASE_URL?.replace(/\/+$/, "");
const SERVICE_KEY = process.env.SUPABASE_SERVICE_ROLE_KEY;
const MAILPIT_URL = (process.env.E2E_MAILPIT_URL ?? "http://127.0.0.1:54324").replace(/\/+$/, "");

/** Anything in a URL that could be spent to sign in. */
const SECRET_IN_URL = /access_token|refresh_token|provider_token|token_hash|[?&#]code=|sb_flow_id/;

test.skip(!SUPABASE_URL || !SERVICE_KEY, "SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY not set — needs the local stack");
test.use({ locale: "en-US" });

function adminHeaders() {
  return { apikey: SERVICE_KEY!, Authorization: `Bearer ${SERVICE_KEY}`, "Content-Type": "application/json" };
}

async function createUser(request: APIRequestContext): Promise<string> {
  const email = `e2e-link-${Date.now()}-${Math.random().toString(36).slice(2, 8)}@equip-ci.invalid`;
  const res = await request.post(`${SUPABASE_URL}/auth/v1/admin/users`, {
    headers: adminHeaders(),
    data: { email, password: `pw-${Math.random().toString(36)}-${Date.now()}`, email_confirm: true },
  });
  expect(res.ok(), await res.text()).toBeTruthy();
  return email;
}

interface GeneratedLink {
  hashedToken: string;
  actionLink: string;
}

async function generateLink(
  request: APIRequestContext,
  type: "magiclink" | "recovery",
  email: string,
  redirectTo?: string,
): Promise<GeneratedLink> {
  const res = await request.post(`${SUPABASE_URL}/auth/v1/admin/generate_link`, {
    headers: adminHeaders(),
    data: { type, email, ...(redirectTo ? { redirect_to: redirectTo } : {}) },
  });
  expect(res.ok(), await res.text()).toBeTruthy();
  const body = (await res.json()) as Record<string, unknown> & { properties?: Record<string, unknown> };
  const props = body.properties ?? body;
  return { hashedToken: String(props.hashed_token), actionLink: String(props.action_link) };
}

async function hasStoredSession(page: Page): Promise<boolean> {
  return page.evaluate(() => Object.keys(window.localStorage).some((k) => /^sb-.+-auth-token$/.test(k)));
}

/** Signed in, moved on from the landing page, and the URL carries nothing. */
async function expectSignedInAndClean(page: Page) {
  await expect.poll(() => hasStoredSession(page), { timeout: 15_000 }).toBe(true);
  await expect(page).not.toHaveURL(/\/auth\/(confirm|callback)|\/login/, { timeout: 15_000 });
  expect(page.url()).not.toMatch(SECRET_IN_URL);
}

test.describe("sign-in links", () => {
  test("the email link signs in from a browser that never asked for it", async ({ page, request }) => {
    const email = await createUser(request);
    const { hashedToken } = await generateLink(request, "magiclink", email);

    await page.goto(`/auth/confirm#token_hash=${encodeURIComponent(hashedToken)}&type=magiclink`);
    await expectSignedInAndClean(page);
  });

  test("a recovery link opens the new-password form, and the token is gone from the URL", async ({
    page,
    request,
  }) => {
    const email = await createUser(request);
    const { hashedToken } = await generateLink(request, "recovery", email);

    await page.goto(`/auth/reset-password#token_hash=${encodeURIComponent(hashedToken)}&type=recovery`);
    await expect(page.getByLabel("New Password", { exact: true })).toBeVisible({ timeout: 15_000 });
    await expect(page).toHaveURL(/\/auth\/reset-password$/);
    expect(page.url()).not.toMatch(SECRET_IN_URL);
    expect(await hasStoredSession(page)).toBe(true);
  });

  test("a link mailed before PKCE still signs in, and its session leaves the URL", async ({
    page,
    request,
    baseURL,
  }) => {
    const email = await createUser(request);
    // The shape every email had until this change: GoTrue's verify endpoint,
    // which answers 303 to `redirect_to#access_token=…&refresh_token=…`.
    const { actionLink } = await generateLink(request, "magiclink", email, `${baseURL}/auth/confirm`);
    expect(actionLink).toContain("/auth/v1/verify");

    const seen: string[] = [];
    page.on("framenavigated", (frame) => {
      if (frame === page.mainFrame()) seen.push(frame.url());
    });
    await page.goto(actionLink);
    await expectSignedInAndClean(page);
    // Proves the test walked the legacy path rather than something else.
    expect(seen.some((u) => u.includes("access_token="))).toBe(true);
  });

  test("a link used twice says it expired", async ({ browser, request }) => {
    const email = await createUser(request);
    const { hashedToken } = await generateLink(request, "magiclink", email);
    const link = `/auth/confirm#token_hash=${encodeURIComponent(hashedToken)}&type=magiclink`;

    const first = await browser.newContext({ locale: "en-US" });
    const firstPage = await first.newPage();
    await firstPage.goto(link);
    await expectSignedInAndClean(firstPage);
    await first.close();

    const second = await browser.newContext({ locale: "en-US" });
    const secondPage = await second.newPage();
    await secondPage.goto(link);
    await expect(secondPage.getByRole("alert")).toHaveText("This link has expired. Request a new one.", {
      timeout: 15_000,
    });
    expect(secondPage.url()).not.toMatch(SECRET_IN_URL);
    expect(await hasStoredSession(secondPage)).toBe(false);
    await second.close();
  });

  test.describe("Email me a link instead, through Mailpit", () => {
    test.beforeAll(async ({ request }) => {
      const reachable = await request
        .get(`${MAILPIT_URL}/api/v1/messages?limit=1`)
        .then((r) => r.ok())
        .catch(() => false);
      test.skip(!reachable, `Mailpit is not reachable at ${MAILPIT_URL}`);
    });

    async function requestLink(page: Page, email: string) {
      await page.goto("/login");
      await page.getByLabel("Email", { exact: true }).fill(email);
      await page.getByRole("button", { name: "Email me a link instead" }).click();
    }

    /** The link in the mail GoTrue sent this address. */
    async function linkFromMail(request: APIRequestContext, email: string): Promise<string> {
      let link: string | undefined;
      await expect
        .poll(
          async () => {
            const search = await request.get(
              `${MAILPIT_URL}/api/v1/search?query=${encodeURIComponent(`to:"${email}"`)}`,
            );
            const { messages } = (await search.json()) as { messages?: { ID: string }[] };
            const id = messages?.[0]?.ID;
            if (!id) return false;
            const message = (await (await request.get(`${MAILPIT_URL}/api/v1/message/${id}`)).json()) as {
              HTML?: string;
              Text?: string;
            };
            const match = `${message.HTML ?? ""}\n${message.Text ?? ""}`.match(
              /(https?:\/\/[^\s"'<>]*\/auth\/v1\/verify[^\s"'<>]*)/,
            );
            link = match?.[1]?.replace(/&amp;/g, "&");
            return Boolean(link);
          },
          { timeout: 20_000, intervals: [500] },
        )
        .toBe(true);
      return link!;
    }

    test("followed in the browser that asked, it comes back as a one-time code", async ({ page, request }) => {
      const email = await createUser(request);
      await requestLink(page, email);
      const link = await linkFromMail(request, email);

      const seen: string[] = [];
      page.on("framenavigated", (frame) => {
        if (frame === page.mainFrame()) seen.push(frame.url());
      });
      await page.goto(link);
      await expectSignedInAndClean(page);
      // PKCE, not implicit: GoTrue sent a code, never a session.
      expect(seen.some((u) => /[?&]code=/.test(u))).toBe(true);
      expect(seen.some((u) => u.includes("access_token="))).toBe(false);
    });

    test("its token hash signs in on another device", async ({ page, browser, request }) => {
      const email = await createUser(request);
      await requestLink(page, email);
      const token = new URL(await linkFromMail(request, email)).searchParams.get("token");
      expect(token).toBeTruthy();

      // A fresh context has no PKCE verifier — the phone the email was
      // opened on. This is the shape send-email builds in production.
      const phone = await browser.newContext({ locale: "en-US" });
      const phonePage = await phone.newPage();
      await phonePage.goto(`/auth/confirm#token_hash=${encodeURIComponent(token!)}&type=magiclink`);
      await expectSignedInAndClean(phonePage);
      await phone.close();
    });
  });
});
