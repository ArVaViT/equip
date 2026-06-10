# Security operational notes

Companion to the top-level [`SECURITY.md`](../SECURITY.md), which is the
public vulnerability-reporting policy. This file is for maintainers --
deployment-side security posture, known limitations of the hosting tier,
and the current backlog of items deferred for cost / plan reasons.

> **Note:** Section headings here use Title Case and are intentionally
> stable -- internal docs link by anchor.

## HaveIBeenPwned leaked-password protection (enabled)

**Status:** ENABLED (2026-06). `password_hibp_enabled: true` on the prod
auth config; the `auth_leaked_password_protection` advisor no longer fires.
Available because the project is on **Supabase Pro** (the feature is gated
to Pro and up; it returned `HTTP 402` while we were on Free).

**Defense in depth around it:**

- Minimum password length is set to **12**.
- Email-based auth verifies ownership via the confirmation email link.
- Most Equip accounts sign in with **Google OAuth**, not email/password
  -- those identities don't enter our password-hash flow at all.
- Rate limiting on `/api/v1/auth/*` (10 req / 60s per IP, plus Vercel
  WAF at the edge) makes credential-stuffing expensive.

Toggle lives at `PATCH /v1/projects/<ref>/config/auth` (or the Supabase
Dashboard) — a single config flag, no schema impact.

## CSP enforcement promotion

**Status:** `Content-Security-Policy-Report-Only` ships from `vercel.json`.
Promotion to enforcing CSP is **not** done yet.

**Why report-only first:** the policy enumerates every external origin
the SPA touches today (`api.equipbible.com`, Supabase, Datadog RUM,
YouTube embeds). It is highly likely we missed something -- a transitive
dep that quietly loads an analytics pixel, a future content block that
points at a new CDN, etc. Enforcing CSP before a real-traffic burn-in
risks a 100%-blocked page for users.

**Promotion checklist (do these in one PR):**

1. Watch `Content-Security-Policy-Report-Only` console violations for a
   week of normal usage (you / staging users / a Datadog RUM query for
   `error.message LIKE "%violated directive%"`).
2. Add any legitimately-blocked origin to the appropriate directive.
3. Rename the header key from `Content-Security-Policy-Report-Only` to
   `Content-Security-Policy` in `frontend/vercel.json`.
4. Update `src/__tests__/vercelCsp.test.ts` -- the "ships as Report-Only,
   not enforcing" assertion needs to flip.
5. Ship; watch Datadog for the first 24h.

## Rate-limiting topology

Two layers exist; both are documented in `app/middleware/rate_limit.py`.

- **Per-instance in-memory limiter** (FastAPI middleware). Cheap and
  zero-dependency. Drawback: Vercel serverless workers don't share
  state, so an attacker distributing requests across cold workers sees
  ~N times the effective budget. Acceptable defense-in-depth at our
  scale (~100 users); not a hard enforcement boundary.
- **Vercel WAF / Edge rate limits** (configured in the Vercel
  Dashboard). The real hard ceiling. Currently configured for
  `/api/v1/auth/*` at 10 req / 60s per IP. Extend via Vercel
  Dashboard -> Firewall -> Rate Limit Rules if a new public surface
  needs it.

If usage crosses ~1000 active users/day, switch the in-memory limiter
to Upstash Redis (`@upstash/ratelimit`) so the per-instance budget
becomes a true shared counter. Estimated overhead: ~5-10 ms per request
and ~$10/mo Upstash minimum.

## Secret hygiene

- The repo MUST NOT contain real values. `.env.example` is a template;
  real values live only in Vercel env vars (and locally in `.env`,
  which is gitignored).
- The **only** Supabase key permitted in the frontend bundle is the
  **publishable / anon** key (`VITE_SUPABASE_ANON_KEY`). The
  **service-role** key MUST stay backend-only -- it bypasses RLS.
  Regression test: `grep -r service_role frontend/src` must return
  nothing.
- The Gemini API key (`GEMINI_API_KEY`) is server-only. It is wrapped
  in `pydantic.SecretStr` so accidental `repr(settings)` logging does
  not leak it.

## Audit logging

`audit_logs` is admin-read-only by RLS
(`audit_logs_select_admin` policy, see
`supabase/migrations/20260421015755_rls_perf_cleanup_016_policies.sql`)
with no INSERT / UPDATE / DELETE policy for client roles -- the
FastAPI backend is the sole writer via `app/services/audit_service.py`.

Privileged actions that write to `audit_logs` today:

- Role change (`PUT /users/admin/users/{id}/role`) -- in
  `app/api/v1/users.py::update_user_role`.
- Bulk role change (`PUT /users/admin/users/bulk-role`).
- Admin user deletion (`DELETE /users/admin/users/{id}`).
- Certificate teacher / admin approval + rejection.
- User locale change (audit-logged because role-elevated users
  flipping languages affects editor visibility).
- Assignment grade changes and enrollment / unenrollment.

If a new privileged action is added (e.g. promote a user to admin via
some new flow), it MUST call `audit_service.log_action` in the same
transaction as the data write. Sharing the transaction guarantees a
single COMMIT either makes both visible or rolls both back -- there is
no window where the change is durable but the audit trail is missing.

## Client Read Surface — RLS Boundary vs Backend Gate

**Decision (2026-06, accepted):** course *content* (course / module /
chapter / block text for non-public, e.g. institute, courses) is readable
at the **RLS layer** by any authenticated user who queries Postgres
directly through `supabase-js`. We **accept** this and gate content
visibility at the **backend (API) layer**, not with per-row RLS policies
keyed on enrollment. This is a deliberate scope decision, not an oversight.

**What the RLS layer DOES hard-enforce** (the real security boundary,
because the browser holds the publishable key + a user JWT and can hit
Postgres directly). All of these are proven every CI run by
`supabase/ci/rls_assertions.sql`, run as the `authenticated` role:

- **Answer keys** — `quiz_options` / `daily_challenge_options` SELECT is
  REVOKED from `anon` + `authenticated` (migrations
  `20260608200000_revoke_client_answer_key_reads`). A direct read can't
  leak `is_correct` before submission; the backend serves stripped options.
- **PII / cross-tenant** — `profiles` SELECT is self-only
  (`profiles_select_self`); another user's row returns 0 rows.
- **Grades / scores** — `student_grades`, `quiz_attempts`,
  `certificates` are not client-writable; a student can't self-grade,
  tamper a score, or self-approve a certificate.
- **Audit trail + privilege** — `audit_logs`, `quiz_extra_attempts`,
  `quiz_answers` writes are revoked from client roles; `profiles.role`
  escalation is blocked by the immutable-fields trigger.

**What is intentionally backend-gated, not RLS-gated:** reading the
*teaching text* of a non-public course. The API filters by publish state
and enrollment (`require_enrollment` / `verify_course_owner` deps); a
caller who bypasses the API and reads the rows directly sees lesson prose
and quiz *prompts* (never the answer key, never another user's data).

**Why accept rather than add per-row content RLS:**

1. The data exposed is teaching material, not secrets — lesson text and
   question prompts, with every actual secret (answer keys, PII, grades,
   audit) already hard-walled above.
2. Equip's product direction is a neutral platform of teacher-uploaded
   courses; content is meant to be readable by enrolled students. Gating
   *reads* of course text behind enrollment needs per-row RLS policies
   joining `enrollments` on every content table (courses, modules,
   chapters, blocks, …) — a large, perf-sensitive surface that would have
   to stay in lockstep with the enrollment model.
3. Blast radius today is one institute course and zero real users.

**Revisit if** Equip ever hosts genuinely confidential paid content where
the lesson text itself (not just credentials) must be enrollment-gated.
At that point add enrollment-keyed RLS policies to the content tables and
extend `rls_assertions.sql` to prove a non-enrolled `authenticated` user
reads 0 content rows.

## Dependency scanning

- Backend: `pip-audit --requirement requirements.txt --strict` runs in
  CI on every push (`.github/workflows/backend-ci.yml`). It audits the
  pinned runtime deps only -- not dev deps, not the host Python env.
  Latest run: clean.
- Frontend: `npm audit --omit=dev --audit-level=high` runs in CI after
  `npm ci` (`.github/workflows/frontend-ci.yml`) — a HIGH/CRITICAL advisory
  on production deps is a hard gate that fails the build. Moderate/low
  advisories are triaged via Dependabot rather than blocking.
- Major-version bumps must be deliberate. Don't blindly run `npm
  outdated --json | jq | xargs npm install` -- breakages from major
  bumps (Vite, React, Pydantic) are common and lose CI signal.
