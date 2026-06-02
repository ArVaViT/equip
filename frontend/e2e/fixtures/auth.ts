/**
 * Auth fixtures for Playwright E2E.
 *
 * The smoke spec hits public-only routes. Anything testing the
 * student / teacher / admin golden paths needs a logged-in browser
 * context. These fixtures cover two strategies:
 *
 * 1. **Storage state from a sign-in flow.** Used by the global
 *    setup (``global.setup.ts``) — exercises the real login form
 *    against the test Supabase project, then saves the session
 *    cookies / localStorage to a JSON file. Every subsequent test
 *    reuses that file. Two perks: fewer sign-in calls hammering
 *    Supabase, and the login form itself is covered by the setup
 *    even when individual specs skip it.
 *
 * 2. **Programmatic session injection.** When a spec wants to
 *    cover a specific user state (e.g. an admin running a
 *    moderation flow) without going through the login UI, the
 *    fixture writes the Supabase session straight into
 *    localStorage. Faster and decoupled from any login-form
 *    regressions in the SUT.
 *
 * Neither path is wired into the CI workflow yet — the CI preview
 * has no real Supabase project. The fixtures land as a structured
 * placeholder so the first golden-path spec can use them once the
 * test Supabase project is provisioned.
 */
import { test as base } from "@playwright/test";
import type { Page, BrowserContext } from "@playwright/test";

export type AuthRole = "student" | "teacher" | "admin";

interface TestUser {
  email: string;
  password: string;
  /** Pre-existing user id in the test project so seed data can
   * reference it without hitting Supabase auth on every spec. */
  id: string;
  role: AuthRole;
}

/**
 * Read the test credentials for a role from env vars. The CI
 * workflow will need to set these once a test Supabase project
 * exists. Local dev can copy them from
 * ``Memory/equip-e2e-test-users.md``.
 */
export function getTestUser(role: AuthRole): TestUser {
  const prefix = `E2E_${role.toUpperCase()}`;
  const email = process.env[`${prefix}_EMAIL`];
  const password = process.env[`${prefix}_PASSWORD`];
  const id = process.env[`${prefix}_ID`];
  if (!email || !password || !id) {
    throw new Error(
      `Missing ${prefix}_EMAIL / _PASSWORD / _ID. ` +
        "These come from the test Supabase project; populate them in CI " +
        "via repository secrets and locally via frontend/.env.local.",
    );
  }
  return { email, password, id, role };
}

/**
 * Sign in through the real login form and return the page in a
 * post-login state. Used by the global setup to mint a storage-state
 * file. Individual specs should NOT call this — they should rely on
 * the storage-state baked into ``playwright.config.ts`` (added once
 * global setup is wired).
 */
export async function signInViaForm(
  page: Page,
  user: TestUser,
): Promise<void> {
  await page.goto("/login");
  await page.getByLabel(/email/i).fill(user.email);
  await page.getByLabel(/password|пароль/i).fill(user.password);
  await page.getByRole("button", { name: /sign in|войти/i }).click();
  // After a successful sign-in the auth gate replaces the root with
  // the dashboard. The header carries an Equip wordmark.
  await page.waitForURL((url) => !url.pathname.startsWith("/login"));
}

/**
 * Inject a Supabase session into localStorage so the SPA boots
 * already authenticated. Faster than the form sign-in and isolated
 * from any login-form regression in the SUT.
 *
 * Constructs a minimal session shape the supabase-js client expects;
 * the access_token MUST be a valid JWT signed by the test project's
 * key. The setup script signs one ahead of time and stuffs it into
 * the env var.
 */
export async function injectSession(
  context: BrowserContext,
  user: TestUser,
  accessToken: string,
): Promise<void> {
  const session = {
    access_token: accessToken,
    refresh_token: "test-refresh-token",
    expires_in: 3600,
    expires_at: Math.floor(Date.now() / 1000) + 3600,
    token_type: "bearer",
    user: {
      id: user.id,
      email: user.email,
      role: "authenticated",
    },
  };
  await context.addInitScript((s) => {
    // supabase-js v2 keys the session under
    // ``sb-<project-ref>-auth-token``. The test project's ref must
    // be supplied at injection time.
    const key = "sb-equip-test-auth-token";
    window.localStorage.setItem(key, JSON.stringify(s));
  }, session);
}

/**
 * Extend Playwright's base test fixture with a couple of helpers
 * that derive a role-bound page object. Usage in a spec:
 *
 *   import { test } from "../fixtures/auth";
 *
 *   test("student can enroll", async ({ studentPage }) => { ... });
 */
export const test = base.extend<{
  studentPage: Page;
  teacherPage: Page;
  adminPage: Page;
}>({
  // For each role, return a page with the role's storage state
  // already loaded. Wired here as a stub; the global setup will fill
  // the storageState files in a follow-up.
  studentPage: async ({ browser }, use) => {
    const ctx = await browser.newContext({
      storageState: "playwright/.auth/student.json",
    });
    const page = await ctx.newPage();
    await use(page);
    await ctx.close();
  },
  teacherPage: async ({ browser }, use) => {
    const ctx = await browser.newContext({
      storageState: "playwright/.auth/teacher.json",
    });
    const page = await ctx.newPage();
    await use(page);
    await ctx.close();
  },
  adminPage: async ({ browser }, use) => {
    const ctx = await browser.newContext({
      storageState: "playwright/.auth/admin.json",
    });
    const page = await ctx.newPage();
    await use(page);
    await ctx.close();
  },
});

export { expect } from "@playwright/test";
