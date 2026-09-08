-- Eight tables were left open.
--
-- Supabase's security advisor has been mailing `rls_disabled_in_public`
-- weekly since at least 18 Aug 2026. The finding is real, but its
-- wording ("anyone can read, edit, and delete") is a template: `anon`
-- holds SELECT on these eight and nothing else, so the exposure was
-- read-only. Measured on production before writing this file, for each
-- of the eight: relrowsecurity false, zero policies, anon SELECT true,
-- anon INSERT/UPDATE/DELETE false.
--
-- What was actually reachable. Six of the eight are empty — the rubric
-- tables and `submission_declarations` ship ahead of the grading UI that
-- will fill them. The two that hold rows are the reason this is not a
-- paperwork fix:
--
--   legal_acceptances (34 rows) — user_id, document_slug, version,
--     accepted_at and **ip**. An account identifier joined to an IP
--     address is personal data, and it sat behind a publishable key.
--   organizations (1 row) — legal_name, country, verification_basis.
--
-- Why enabling RLS with no policies is the whole fix, and safe. These
-- tables are owned by `postgres`, relforcerowsecurity is false, and
-- `postgres` carries BYPASSRLS; the backend reaches Postgres over
-- DATABASE_URL as that role, and its PostgREST calls use the
-- service-role key, which bypasses RLS as well. See the note at the top
-- of 20260830040000_rls_learns_about_organizations.sql — the same
-- reasoning, from the other direction. The browser bundle never asks
-- for any of these eight: the only tables `frontend/src/lib/supabase.ts`
-- reads are profiles, enrollments and courses. So RLS on with no policy
-- is deny-all for `anon` and `authenticated`, and a no-op for every
-- path that serves a user today.
--
-- Deliberately not done here: writing SELECT policies. When the grading
-- UI needs a rubric in the browser, the policy is written then, against
-- a real query, rather than guessed now — a policy invented ahead of its
-- caller is the kind that gets written `USING (true)`.

ALTER TABLE public.legal_acceptances       ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.organizations           ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.submission_declarations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.rubrics                 ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.rubric_criteria         ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.rubric_levels           ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.rubric_marks            ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.assignment_rubrics      ENABLE ROW LEVEL SECURITY;
