-- A director is not a platform admin.
--
-- Today one role opens two doors. Forty-five routes are gated by
-- `require_admin`, and they are two unrelated things: twenty-six belong
-- to an organization — cohorts, ведомости, invitations, certificates,
-- its own settings — and nineteen belong to the platform: the
-- translation queue, user administration, health, the audit log.
--
-- With one organization that is harmless. With two it is a leak: the
-- person who closes their own ведомость would, by the same right,
-- re-open the translation queue of the whole platform and read every
-- other organization's audit log.
--
-- So `director` arrives before organizations do. Nothing is assigned to
-- it by this migration: it widens the domain so the routes can move,
-- and the move is what the application code does next. Splitting the
-- role after the column exists would mean auditing every route twice.
--
-- See engineering/organizations-engineering-plan.md §2 in equipbible-docs.

ALTER TABLE public.profiles
    DROP CONSTRAINT IF EXISTS chk_profiles_role;

ALTER TABLE public.profiles
    ADD CONSTRAINT chk_profiles_role
    CHECK (role = ANY (ARRAY['admin'::text, 'director'::text, 'teacher'::text, 'student'::text]));
