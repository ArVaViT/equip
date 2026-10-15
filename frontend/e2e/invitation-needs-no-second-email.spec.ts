/**
 * An invitation opens an account, against a real GoTrue.
 *
 * The unit tests fake Supabase Auth; this walks the real admin API the
 * backend now calls, through the local stack `frontend-e2e.yml` boots:
 *
 *   - a new address: the form creates the account, signs in, and lands
 *     where the invitation leads, with no email in between;
 *   - an address somebody signed up with and never confirmed: the link
 *     confirms it, and the password typed now is the one that works —
 *     Supabase's own repeated sign-up keeps the first one;
 *   - an address with a confirmed account: the page asks to sign in, the
 *     sign-in page comes back, and the invitation is accepted on arrival.
 *
 * The link's token is derived from the invitation's id with a key derived
 * from the backend's JWT secret (`invitation_service.invitation_token`) —
 * the mail that carries it is not sent here, so the spec derives it the same
 * way.
 */
import { createHmac, randomBytes, randomUUID } from "node:crypto";

import { test, expect, type APIRequestContext, type Page } from "@playwright/test";

const SUPABASE_URL = process.env.SUPABASE_URL?.replace(/\/+$/, "");
const SERVICE_KEY = process.env.SUPABASE_SERVICE_ROLE_KEY;
const ANON_KEY = process.env.SUPABASE_ANON_KEY;
const JWT_SECRET = process.env.JWT_SECRET_KEY;
const API_URL = (process.env.E2E_API_URL ?? "http://127.0.0.1:8000").replace(/\/+$/, "");
const ADMIN_EMAIL = process.env.E2E_ADMIN_EMAIL;
const ADMIN_PASSWORD = process.env.E2E_ADMIN_PASSWORD;

test.skip(
  !SUPABASE_URL || !SERVICE_KEY || !ANON_KEY || !JWT_SECRET || !ADMIN_EMAIL || !ADMIN_PASSWORD,
  "needs the local stack: SUPABASE_*, JWT_SECRET_KEY and the E2E admin",
);
test.use({ locale: "en-US" });

function adminHeaders() {
  return { apikey: SERVICE_KEY!, Authorization: `Bearer ${SERVICE_KEY}`, "Content-Type": "application/json" };
}

async function passwordGrant(request: APIRequestContext, email: string, password: string) {
  return request.post(`${SUPABASE_URL}/auth/v1/token?grant_type=password`, {
    headers: { apikey: ANON_KEY!, "Content-Type": "application/json" },
    data: { email, password },
  });
}

/** A platform invitation written by the e2e admin, and the link it mails. */
async function invite(request: APIRequestContext, email: string): Promise<string> {
  const session = await passwordGrant(request, ADMIN_EMAIL!, ADMIN_PASSWORD!);
  expect(session.ok(), await session.text()).toBeTruthy();
  const { access_token: accessToken } = (await session.json()) as { access_token: string };
  const res = await request.post(`${API_URL}/api/v1/invitations`, {
    headers: { Authorization: `Bearer ${accessToken}`, "Content-Type": "application/json" },
    data: { email, role: "student", scope: "platform", age_attested: true },
  });
  expect(res.ok(), await res.text()).toBeTruthy();
  const { id } = (await res.json()) as { id: string };
  const key = createHmac("sha256", JWT_SECRET!).update("equip-invitation-link").digest();
  const token = createHmac("sha256", key).update(id).digest("base64url");
  return `/invite/accept#token=${token}`;
}

async function hasStoredSession(page: Page): Promise<boolean> {
  return page.evaluate(() => Object.keys(window.localStorage).some((k) => /^sb-.+-auth-token$/.test(k)));
}

async function createAccount(page: Page, password: string) {
  await page.getByLabel("Full name").fill("Invited Person");
  await page.locator("#invite-password").fill(password);
  const confirm = page.locator("#invite-confirmPassword");
  if (await confirm.count()) await confirm.fill(password);
  await page.getByRole("button", { name: "Create account" }).click();
}

test.describe("an invitation needs no second email", () => {
  test("a new address: account, sign-in and arrival in one step", async ({ page, request }) => {
    const email = `e2e-invite-${randomUUID()}@equip-ci.invalid`;
    const link = await invite(request, email);

    await page.goto(link);
    await createAccount(page, randomBytes(18).toString("base64url"));

    await expect.poll(() => hasStoredSession(page), { timeout: 15_000 }).toBe(true);
    await expect(page).toHaveURL(/\/$/, { timeout: 15_000 });
  });

  test("an unconfirmed address: confirmed by the link, with the password typed now", async ({ page, request }) => {
    const email = `e2e-invite-${randomUUID()}@equip-ci.invalid`;
    const firstPassword = randomBytes(18).toString("base64url");
    const created = await request.post(`${SUPABASE_URL}/auth/v1/admin/users`, {
      headers: adminHeaders(),
      data: { email, password: firstPassword, email_confirm: false },
    });
    expect(created.ok(), await created.text()).toBeTruthy();
    const link = await invite(request, email);

    const newPassword = randomBytes(18).toString("base64url");
    await page.goto(link);
    await createAccount(page, newPassword);

    await expect.poll(() => hasStoredSession(page), { timeout: 15_000 }).toBe(true);
    expect((await passwordGrant(request, email, newPassword)).ok()).toBe(true);
    expect((await passwordGrant(request, email, firstPassword)).ok()).toBe(false);
  });

  test("a confirmed address: sign in, and the invitation is accepted on the way back", async ({
    page,
    request,
  }) => {
    const email = `e2e-invite-${randomUUID()}@equip-ci.invalid`;
    const password = randomBytes(18).toString("base64url");
    const created = await request.post(`${SUPABASE_URL}/auth/v1/admin/users`, {
      headers: adminHeaders(),
      data: { email, password, email_confirm: true },
    });
    expect(created.ok(), await created.text()).toBeTruthy();
    const link = await invite(request, email);

    await page.goto(link);
    await page.getByRole("link", { name: "Sign In" }).click();
    await expect(page.getByLabel("Email")).toHaveValue(email);
    await page.getByLabel("Password", { exact: true }).fill(password);
    await page.getByRole("button", { name: "Sign In" }).click();

    await expect.poll(() => hasStoredSession(page), { timeout: 15_000 }).toBe(true);
    await expect(page).toHaveURL(/\/$/, { timeout: 15_000 });
  });
});
