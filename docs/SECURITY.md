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

**Status:** ENFORCING (promoted June 2026). `frontend/vercel.json` ships
a real `Content-Security-Policy` header -- the Report-Only burn-in
surfaced no violations and the header key was flipped.
`frontend/src/__tests__/vercelCsp.test.ts` asserts the enforcing header
is present and that the report-only key has not been reintroduced.

**When adding a new external origin** (a new CDN, analytics endpoint,
embed host, etc.): extend the matching directive in
`frontend/vercel.json` AND update `vercelCsp.test.ts` in the same PR --
the test enumerates the allowed origins, so a directive change without
the test change fails CI.

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
(`audit_logs_select_admin` policy; introduced in
`supabase/migrations/20260421015755_rls_perf_cleanup_016_policies.sql`,
current text in `supabase/schema.sql`)
with no INSERT / UPDATE / DELETE policy for client roles -- the
FastAPI backend is the sole writer via `app/services/audit_service.py`.

Privileged actions that write to `audit_logs` today:

- Role change (`PUT /users/admin/users/{id}/role`) -- in
  `app/api/v1/users.py::update_user_role`.
- Bulk role change (`PUT /users/admin/users/bulk-role`).
- Admin user deletion and restore (`DELETE /users/admin/users/{id}`, `POST /users/admin/users/{id}/restore`).
- Certificate approval + rejection -- the teacher step and the
  director step (`require_director`: an organization's director, or a
  platform admin).
- Invitations (create, revoke, accept) -- `app/services/invitation_service.py`.
- Organizations and organization settings (`admin_organizations.py`,
  `admin_org_settings.py`).
- Cohort and course writes, rubric changes, admin translation actions.
- User locale change (audit-logged because role-elevated users
  flipping languages affects editor visibility).
- Assignment grade changes, progress edits, enrollment / unenrollment.

The authoritative list is `grep -rn "log_action(" backend/app` -- this
prose has fallen behind it once already.

If a new privileged action is added (e.g. promote a user to admin via
some new flow), it MUST call `audit_service.log_action`.

What the trail guarantees today, and what it does not (checked
2026-09-30 against the code, not the intent this section used to state):

- `log_action` is best-effort. It writes inside a SAVEPOINT and then
  commits; if the write fails it logs `Failed to write audit log` (an
  ERROR, which reaches Datadog) and returns. The request succeeds.
- Most callers commit their own change first and call `log_action`
  after, so there is a window in which the change is durable and its
  audit row is not yet written, and a failed audit write leaves the
  change without a row.
- A caller that invokes `log_action` with its change still pending gets
  that change committed by `log_action`'s commit, and on an audit failure
  rolled back by its rollback (organization create in
  `admin_organizations.py`). One that logs before making the change
  (user deactivation in `users.py`) can leave a row for a change whose
  own commit then failed.

So a missing row is possible and shows up as that ERROR in the logs.
Making privileged actions fail when their audit row cannot be written
is an open item (engineering audit 2026-09-30, P1-6).

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
  tamper a score, or self-approve a certificate. (Subsumed by the
  blanket write lockdown below.)
- **Audit trail + privilege** — `audit_logs`, `quiz_extra_attempts`,
  `quiz_answers` writes are revoked from client roles (likewise subsumed
  by the lockdown below); `profiles.role` escalation is blocked by the
  immutable-fields trigger.

**Client Write Surface (server-only since 2026-06-11):** migration
`20260611200000_server_only_writes_lockdown` revoked
INSERT / UPDATE / DELETE / TRUNCATE on **all** public tables from `anon`
+ `authenticated`, dropped the 22 write policies those revokes made
inert, and flipped DEFAULT PRIVILEGES so tables created by future
migrations are born without client write grants. The **only** remaining
client write is the `profiles` safe-fields UPDATE (row-scoped by policy,
column-protected by `trg_profiles_protect_immutable_fields`). As defense
in depth, the public `/certificates/verify` endpoint additionally honors
only rows with `status='approved'` -- a forged row in any other status is
never reported valid. Enforcement is asserted every CI run by 10 denial
probes in `supabase/ci/rls_assertions.sql` (certificate forgery, attempt
/ answer fabrication, progress faking, enrollment deletion, and more).

**What is intentionally backend-gated, not RLS-gated:** reading the
*teaching text* of a non-public course. The API filters by publish state
and enrollment (`lookup_enrollment` / `verify_chapter_access` /
`verify_course_owner` deps in `app/api/dependencies.py`); a
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
3. Blast radius is course *teaching text* only. Real pilot users exist
   since 2026-06-10, but every actual secret (answer keys, PII, grades,
   audit trail) is already hard-walled at the RLS layer above -- what a
   direct reader can reach is lesson prose and question prompts.

**Revisit if** Equip ever hosts genuinely confidential paid content where
the lesson text itself (not just credentials) must be enrollment-gated.
At that point add enrollment-keyed RLS policies to the content tables and
extend `rls_assertions.sql` to prove a non-enrolled `authenticated` user
reads 0 content rows.

## SECURITY DEFINER helpers are not callable by `anon` (2026-09-15)

`can_teach()`, `current_organization_id()` and `is_platform_staff()` run
with their owner's rights, bypassing RLS. All three had EXECUTE granted to
`anon`, so anyone could invoke them over PostgREST RPC without signing in.

**The grant was real, the exposure was not.** Called as `anon` they return
`false`, `null`, `false` — verified against production inside a rolled-back
transaction. Each reads `auth.uid()`, which is null without a JWT, and
`id = null` is never true.

**Why it happened**, because the same trap is easy to fall into again:
Supabase grants EXECUTE on every new function in `public` to `anon` and
`authenticated` **directly**, separately from the PUBLIC pseudo-role. So the
`REVOKE ... FROM PUBLIC` in `20260830040000_rls_learns_about_organizations`
did not do what it reads like — it dropped the PUBLIC grant and left
Supabase's grant to `anon` untouched. `REVOKE ... FROM PUBLIC` alone never
closes a function. Name `anon` explicitly.

Closed by `20260915030000_anon_loses_execute_on_three_definer_functions`,
applied to production the same day. `authenticated` and `service_role` keep
their own explicit grants. Every policy calling these helpers is
`TO authenticated`; the `course_assets_teacher_*` storage policies evaluate
false for `anon` either way.

**Still open (low priority):** `course_assets_teacher_*` and
`avatars_owner_*` carry no `TO` clause, so they formally apply to `anon`
with an always-false expression. Writing `TO authenticated` would say what
is meant.

## A closed account holds no role (2026-10-19)

An account its owner deleted (`DELETE /users/me`) or an administrator
switched off (`deactivated_at`) keeps its Supabase session on purpose: it
is not banned in GoTrue (a ban would answer `user_banned` before the
password and tell anybody typing the address that it belongs to a deleted
Equip account), and the session is the door back for a self-restore. The
API refuses every call of such a session (`refuse_if_closed`) and the
profile trigger freezes its row.

Until `20261019120000_a_closed_account_holds_no_role` the RLS layer did
not know. The definer helpers every policy asks -- `can_teach()`,
`is_platform_staff()`, `is_staff_of()`, `is_member_of()` -- read
`profiles.role` and the membership rows, which deletion does not touch, so
with the publishable key and the session it still held a closed account
read as the staff it used to be: a suspended director still read the
school's certificates and cohorts through PostgREST, a teacher who deleted
their account still passed `course_assets_teacher_insert` on Storage, a
switched-off administrator still read `audit_logs`. The helpers now also
require `deactivated_at IS NULL` (a deleted account is always deactivated,
by `profiles_deleted_is_deactivated_check`); the two policies that spelled
the admin check out by hand (`audit_logs_select_admin`,
`course_events_select`) call the helper instead. Own rows
(`user_id = auth.uid()`) stay readable -- the export and the restore
screen need them. Section 18 of `supabase/ci/rls_assertions.sql` proves
both directions: switched off, nothing; switched back on, everything.

**Rule for new policies:** never test `profiles.role` or
`organization_members` inline -- call the helper, so a closed account is
closed everywhere at once. A structural guard at the end of section 18
fails CI on a policy that names either table. Wrap a helper that takes
nothing from the row as `(SELECT public.is_platform_staff())`: the planner
then evaluates it once per statement instead of once per row.

The same review found the bucket half-closed: `course_assets_teacher_insert`
asks `can_teach()`, but since 20261016011000 UPDATE and DELETE on
`course-assets` go by `owner_id` and `courses.created_by`, which a closed
account keeps -- so a teacher who deleted their account could still
overwrite or remove the covers and lesson images of the courses they left
behind. `20261019130000_a_closed_account_touches_no_course_file` puts
`can_teach()` in front of both. Storage policies are not in
`schema.sql` and have no CI probe; the fix was proven against a local
stand-in of `storage.objects` (closed: 0 rows written; restored: all).

The private bucket next to it, `course-materials` (lesson files, served
through a signed URL only), was still as 20260227031530 wrote it: the
administrator spelled out by hand (`profiles.role = 'admin'`), the owner by
`courses.created_by`, the student by an `enrollments` row -- none of which
a closed account loses -- and no `TO` clause. So a switched-off or deleted
administrator, course owner or enrolled student still read the files, and
the first two still wrote them.
`20261023230000_a_closed_account_touches_no_course_material` rewrites the
four policies the way the sibling bucket's read: `(SELECT
public.is_platform_staff())` for the administrator, `(SELECT
public.can_teach())` in front of every write, `TO authenticated`, and for
SELECT -- where an enrolled student is inside no role helper -- a new one,
`(SELECT public.is_open_account())`: the account is not deactivated, and
nothing about a role. The `avatars` write policies ask it too (the folder
is the account's own, which a closed account keeps). For an open account
nothing changes (a demoted owner loses the writes, as on `course-assets`;
the editor and the API already refuse them). Section 19 of
`supabase/ci/rls_assertions.sql` builds a stand-in of `storage.objects`,
replays the migration onto it and probes it as an open and a closed
administrator, owner and student -- the first CI probe of a storage
policy -- and extends the rule above to storage: no storage policy names
`profiles` or `organization_members`. Accepted remainder: a signed URL
minted before the account closed keeps working until it expires
(`SIGNED_URL_TTL_SECONDS`, one hour) -- Storage checks the signature, not
these policies.

**The public buckets have no UPDATE policy, on purpose** (same migration;
found in its review). Storage's move and copy (`POST /object/move`, with
`destinationBucket`) are one UPDATE of `storage.objects` under the
caller's role, and permissive UPDATE policies are OR-ed: the row leaving
`course-materials` passed its owner's policy, and the new row, now in
`avatars` under the caller's own folder, passed `avatars_owner_update`;
from there the same step reached `course-assets`. A move checks neither
the target bucket's MIME list nor its size limit, so the owner of a course
could publish a 50 MB private PDF or recording on equipbible.com through
`/img/course-assets/...`. `avatars_owner_update` and
`course_assets_teacher_update` are dropped and not recreated. Nothing used
them: covers and avatars are uploaded under a fresh key and the old one is
removed (`upload` with `upsert: false`, `remove`; no `move`, `copy`,
`update` or `upsert` anywhere in the frontend, the backend or the e2e
specs). So upsert, rename and move in `avatars` and `course-assets` are
refused -- a new write there is a new key. A file in `course-materials`
can still be renamed inside the bucket by its course's owner; its UPDATE
policy checks the new row, and no other UPDATE policy remains to admit a
row elsewhere. Section 19 probes both moves and guards against an UPDATE
policy returning to a public bucket.

**Every INSERT policy asks the type**
(`20261024142623_a_bucket_admits_only_its_own_types_however_the_file_arrives`).
A copy is not an UPDATE: `POST /object/copy` is a SELECT of the source and
a rolled-back INSERT of the destination row under the caller's role, and,
like a move, it never checks the destination bucket's MIME list or size
limit. The row carries the source's `metadata`, or the
`metadata.mimetype` the caller names. An upload to a key ending in
`.emptyFolderPlaceholder` skips the MIME check too. So an enrolled student
could copy a course's PDF into their own `avatars` folder, and anyone who
may insert into a public bucket could store `image/svg+xml`,
`application/xhtml+xml` or `text/javascript` there, served from
equipbible.com. The INSERT policies of all three buckets now require
`metadata->>'mimetype'` to be one of exactly the bucket's
`allowed_mime_types`; an ordinary upload already met that, by the same
exact comparison, before the policy ran. `course_assets_teacher_insert`
also asks where, as SELECT and DELETE there do: the folder of a course the
teacher owns, or `content-images/`; platform staff anywhere. **Rule:** a
bucket's list and its INSERT policy change together, and
`frontend/src/lib/uploadLimits.ts` with them. Section 20 probes copies and
uploads of every kind and fails CI on a storage INSERT policy that does
not name `mimetype`. Accepted remainder: the size limit is still not
checked on a copy -- a copied file must now call itself an image and is
served as one.

**`organization-logos` is the fourth bucket** (2026-10-24,
`20261024033327_an_organization_has_a_logo_folder`): the avatars bucket
with the organization in the person's place -- public, 2 MB, jpeg/png/
webp/gif (no SVG on a bucket served from equipbible.com), one folder per
organization named by its id. SELECT, INSERT and DELETE go to the
organization's director (`is_director_of()`) or platform staff
(`is_platform_staff()`), both false for a closed account; no UPDATE
policy, as on the other public buckets. INSERT also requires
`metadata->>'mimetype'` to be one of the bucket's four types: a copy
(`POST /object/copy`) and an upload to a `.emptyFolderPlaceholder` key
skip the bucket's own MIME check and are decided by that policy alone.
The folder is cast to uuid behind
a CASE, so a key whose first segment is no uuid (every `course-materials`
key, which the same policy is evaluated against) is a refusal and never an
error. `PATCH /organizations/{id}/profile` accepts a `logo_url` only of
the shape `/img/organization-logos/<that id>/<one ASCII segment>` -- the
column cannot point at another organization's folder or at a picture
hosted elsewhere. Section 21 of `rls_assertions.sql` probes the bucket as
a director, a teacher who directs nothing, staff, a student, a closed
director and anon; the `/img/` proxy (`frontend/vercel.json`,
`frontend/vite.config.ts`) names the bucket. Nothing is uploaded today:
the infrastructure exists and every logo stays empty, like a new profile's
photo (decided 2026-10-23).

## Dependency scanning

- Backend: `pip-audit --requirement requirements.txt --strict` runs in
  CI on every push (`.github/workflows/backend-ci.yml`). It audits the
  pinned runtime deps only -- not dev deps, not the host Python env.
  Latest run: clean.
- Frontend: `audit-ci --high --skip-dev` runs in CI after `npm ci`
  (`.github/workflows/frontend-ci.yml`) — a HIGH/CRITICAL advisory on
  production deps is a hard gate that fails the build. The workflow
  carries an explicit `--allowlist` for advisories that were reviewed and
  accepted (two today: react-router RSC mode and braces via tailwindcss);
  every entry there is a decision, not a silence.
  Moderate/low advisories are triaged via Dependabot rather than blocking.
- Major-version bumps must be deliberate. Don't blindly run `npm
  outdated --json | jq | xargs npm install` -- breakages from major
  bumps (Vite, React, Pydantic) are common and lose CI signal.
