-- An account belongs to several organizations.
--
-- Decision 1 of engineering/organizations-engineering-plan.md (2026-08-26)
-- was one organization per account, through `profiles.organization_id`,
-- with the signal that would change it written next to it: the first
-- person who asks. The director of UCOAT asked — he had to give up the
-- director role to be able to teach, because the role was a column on the
-- account and the account sat in exactly one place. This migration puts
-- membership where it belongs: one row per (person, organization), with
-- the role held *there*.
--
-- Phase 1 of 4. Only additive: the new table, the new columns, the helper
-- functions, a backfill from the column, and a trigger that keeps
-- `profiles.role` equal to the person's highest active membership role.
-- Nothing reads the new table yet — the backend of the previous release
-- keeps reading and writing `profiles.organization_id`, and the trigger
-- reproduces exactly the roles it already has. The policies that still say
-- `current_organization_id()` are replaced in phase 3, and the column goes
-- in phase 4, a week after the backend has stopped writing it.
--
-- What `profiles.role` now means: the most a person may do anywhere on the
-- platform — `can_teach()`, `is_platform_staff()`, the storage policies and
-- some hundred and fifty call sites in the application ask exactly that
-- question. `admin` stays a platform role, set only by the admin route and
-- never touched by the mirror. For everyone else the column is a mirror of
-- `organization_members`: `director > teacher > student`, `student` for a
-- person with no membership at all. Which organization, and whether they
-- direct *this* one, is answered by the table.

-- ---------------------------------------------------------------------
-- The table
-- ---------------------------------------------------------------------
--
-- One role per pair rather than a set of roles: the application already
-- treats the roles as nested (``TEACHING_ROLES`` includes the director;
-- ``higher_role`` is a reach ordering), and a set would allow "director
-- but not teacher", a state the product does not distinguish.
--
-- `status` rather than deleting the row: a director who suspends a student
-- or a teacher keeps the record of who brought them in and when, as
-- `deactivated_at` does on `profiles`. Platform `admin` is deliberately not
-- a membership role — see 20260826120000_a_director_is_not_a_platform_admin.
--
-- `joined_via` answers "how did this person get here": a named invitation,
-- a director's appointment, a reusable join link (phase 6 — the link table
-- and the `join_link_id` column arrive with it), or this backfill.

CREATE TABLE IF NOT EXISTS public.organization_members (
    user_id uuid NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    organization_id uuid NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
    role text NOT NULL,
    status text NOT NULL DEFAULT 'active',
    joined_at timestamptz NOT NULL DEFAULT now(),
    invited_by uuid REFERENCES public.profiles(id) ON DELETE SET NULL,
    joined_via text NOT NULL,
    CONSTRAINT organization_members_pkey PRIMARY KEY (user_id, organization_id),
    CONSTRAINT organization_members_role_check
        CHECK (role = ANY (ARRAY['director'::text, 'teacher'::text, 'student'::text])),
    CONSTRAINT organization_members_status_check
        CHECK (status = ANY (ARRAY['active'::text, 'suspended'::text])),
    CONSTRAINT organization_members_joined_via_check
        CHECK (joined_via = ANY (ARRAY['invitation'::text, 'join_link'::text, 'appointment'::text, 'migration'::text]))
);

-- The primary key already answers "where does this person belong". This
-- one answers the organization's questions — its directors, its member
-- count, its staff — without reading the suspended rows.
CREATE INDEX IF NOT EXISTS ix_organization_members_org_role
    ON public.organization_members (organization_id, role) WHERE status = 'active';

COMMENT ON TABLE public.organization_members IS
    'One row per (person, organization). The role is held here; profiles.role '
    'mirrors the highest active one (see mirror_profile_role). Written only by '
    'the backend; a client reads its own rows.';

-- A person may read their own memberships — "my organizations" on the
-- profile page, as `profiles_select_self` lets them read their own row.
-- Nothing else: another member's row is another person's business, and
-- every write goes through the API as the service role. There is no
-- UPDATE policy, so no immutable-fields trigger is needed either.
ALTER TABLE public.organization_members ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.organization_members FROM anon, authenticated;
GRANT SELECT ON TABLE public.organization_members TO authenticated;

DROP POLICY IF EXISTS organization_members_select_self ON public.organization_members;
CREATE POLICY organization_members_select_self ON public.organization_members
    FOR SELECT TO authenticated
    USING (user_id = (SELECT auth.uid()));

-- ---------------------------------------------------------------------
-- What an organization says about itself
-- ---------------------------------------------------------------------
--
-- The public page (phase 4) prints these. One `description` in the
-- organization's own language, like `public_name`, which is deliberately
-- not localized either (resolve_for_display.py); 280 characters is a
-- paragraph that fits a card and an `og:description`. `website_url` is
-- https only: the page links to it, and a link to a plain-http site from
-- a page that says "verified" is the platform vouching for a downgrade.
-- `show_member_count` is the director's switch for the one number on the
-- page that is about people rather than about the organization.

ALTER TABLE public.organizations
    ADD COLUMN IF NOT EXISTS description text,
    ADD COLUMN IF NOT EXISTS logo_url text,
    ADD COLUMN IF NOT EXISTS website_url text,
    ADD COLUMN IF NOT EXISTS show_member_count boolean NOT NULL DEFAULT true;

ALTER TABLE public.organizations DROP CONSTRAINT IF EXISTS organizations_description_length_check;
ALTER TABLE public.organizations
    ADD CONSTRAINT organizations_description_length_check
        CHECK (description IS NULL OR char_length(description) <= 280);

ALTER TABLE public.organizations DROP CONSTRAINT IF EXISTS organizations_website_url_https_check;
ALTER TABLE public.organizations
    ADD CONSTRAINT organizations_website_url_https_check
        CHECK (website_url IS NULL OR website_url ~ '^https://');

-- ---------------------------------------------------------------------
-- Who is asking, and where do they belong
-- ---------------------------------------------------------------------
--
-- The membership-aware replacements for `current_organization_id()`, by
-- the shape of 20260830040000_rls_learns_about_organizations: SECURITY
-- DEFINER so a policy's lookup does not meet the table's own RLS, STABLE
-- so the planner evaluates them once per statement, `search_path` pinned,
-- and EXECUTE taken from `anon` outright (20260915030000 explains why the
-- REVOKE FROM PUBLIC alone did not do that).
--
-- Every one of them answers `false` for a NULL argument. The rule that
-- "NULL never satisfies an organization comparison" used to depend on the
-- author of each policy remembering to write `IS NOT NULL AND`; here it is
-- inside the function, once.
--
-- Nothing calls them yet. Phase 3 rewrites the three policies to do so.

CREATE OR REPLACE FUNCTION public.member_organization_ids()
RETURNS SETOF uuid
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
    SELECT organization_id FROM public.organization_members
    WHERE user_id = (SELECT auth.uid()) AND status = 'active';
$$;

CREATE OR REPLACE FUNCTION public.is_member_of(org uuid)
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
    SELECT org IS NOT NULL AND EXISTS (
        SELECT 1 FROM public.organization_members
        WHERE user_id = (SELECT auth.uid()) AND organization_id = org AND status = 'active'
    );
$$;

CREATE OR REPLACE FUNCTION public.is_staff_of(org uuid)
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
    SELECT org IS NOT NULL AND EXISTS (
        SELECT 1 FROM public.organization_members
        WHERE user_id = (SELECT auth.uid()) AND organization_id = org AND status = 'active'
          AND role IN ('teacher', 'director')
    );
$$;

CREATE OR REPLACE FUNCTION public.is_director_of(org uuid)
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
    SELECT org IS NOT NULL AND EXISTS (
        SELECT 1 FROM public.organization_members
        WHERE user_id = (SELECT auth.uid()) AND organization_id = org AND status = 'active'
          AND role = 'director'
    );
$$;

COMMENT ON FUNCTION public.member_organization_ids() IS
    'Every organization the signed-in account is an active member of, in any role.';
COMMENT ON FUNCTION public.is_member_of(uuid) IS
    'Active member of this organization in any role. false for NULL — a NULL '
    'organization must never satisfy a comparison.';
COMMENT ON FUNCTION public.is_staff_of(uuid) IS
    'Active teacher or director of this organization. false for NULL.';
COMMENT ON FUNCTION public.is_director_of(uuid) IS
    'Active director of this organization. false for NULL. Platform admin is '
    'not a membership role: policies say is_platform_staff() OR is_director_of().';

REVOKE EXECUTE ON FUNCTION public.member_organization_ids() FROM PUBLIC, anon;
REVOKE EXECUTE ON FUNCTION public.is_member_of(uuid) FROM PUBLIC, anon;
REVOKE EXECUTE ON FUNCTION public.is_staff_of(uuid) FROM PUBLIC, anon;
REVOKE EXECUTE ON FUNCTION public.is_director_of(uuid) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.member_organization_ids() TO authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.is_member_of(uuid) TO authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.is_staff_of(uuid) TO authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.is_director_of(uuid) TO authenticated, service_role;

-- ---------------------------------------------------------------------
-- The mirror
-- ---------------------------------------------------------------------
--
-- `profiles.role` = the highest active membership role, `student` with
-- none, and `admin` left alone. One function holds the rule; the trigger
-- only says whom to run it for. The backend repeats the same computation
-- after each membership write it makes (the test database is SQLite and
-- has no triggers), which is harmless: both sides compute the same value.
--
-- SECURITY DEFINER so the UPDATE on `profiles` runs as the owner whoever
-- changed the membership. `profiles_protect_immutable_fields` refuses a
-- role change only from `authenticated`, and nothing but the backend
-- writes memberships — but a guard that holds by construction is better
-- than one that holds by the current list of writers.

CREATE OR REPLACE FUNCTION public.mirror_profile_role(p_user uuid)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
  mirrored text;
BEGIN
  SELECT m.role INTO mirrored
  FROM public.organization_members AS m
  WHERE m.user_id = p_user AND m.status = 'active'
  ORDER BY CASE m.role WHEN 'director' THEN 2 WHEN 'teacher' THEN 1 ELSE 0 END DESC
  LIMIT 1;
  mirrored := COALESCE(mirrored, 'student');
  UPDATE public.profiles
     SET role = mirrored
   WHERE id = p_user AND role <> 'admin' AND role <> mirrored;
END;
$$;

CREATE OR REPLACE FUNCTION public.organization_members_mirror_profile_role()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
BEGIN
  IF TG_OP IN ('INSERT', 'UPDATE') THEN
    PERFORM public.mirror_profile_role(NEW.user_id);
  END IF;
  -- A row that moved to another person, or went away, changes the old
  -- person's answer too.
  IF TG_OP = 'DELETE' OR (TG_OP = 'UPDATE' AND OLD.user_id IS DISTINCT FROM NEW.user_id) THEN
    PERFORM public.mirror_profile_role(OLD.user_id);
  END IF;
  RETURN NULL;
END;
$$;

COMMENT ON FUNCTION public.mirror_profile_role(uuid) IS
    'profiles.role := highest active organization_members.role (director > teacher '
    '> student), student with none; admin is never touched. See 20261003165050.';

REVOKE EXECUTE ON FUNCTION public.mirror_profile_role(uuid) FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION public.organization_members_mirror_profile_role() FROM PUBLIC, anon, authenticated;

-- ---------------------------------------------------------------------
-- Backfill, then prove the mirror changes nothing, then switch it on
-- ---------------------------------------------------------------------
--
-- Everyone who sits in an organization today becomes its member in the
-- role they hold. The one exception is platform staff: an admin who sits
-- in UCOAT becomes its teacher — they do teach there — and never its
-- director by default. Directing is appointed, by hand, in the admin
-- panel; the founder is not an exception to the admission model
-- (admission-organizations-and-teachers.md §6).

INSERT INTO public.organization_members (user_id, organization_id, role, joined_via, joined_at)
SELECT p.id,
       p.organization_id,
       CASE p.role WHEN 'admin' THEN 'teacher' ELSE p.role END,
       'migration',
       COALESCE(p.created_at, now())
  FROM public.profiles AS p
 WHERE p.organization_id IS NOT NULL
ON CONFLICT DO NOTHING;

-- Before the trigger exists: for every non-admin, the role the mirror
-- would write must equal the role they have. The only way it cannot is a
-- teacher or director with no organization — the plan says there are
-- none (20260827100000 filed everybody under UCOAT), and this proves it
-- rather than assuming it. A mismatch aborts the whole migration; the
-- people it names are filed by hand and the file is run again.
DO $$
DECLARE
  bad integer;
  who text;
BEGIN
  SELECT count(*), string_agg(p.id::text || ' (' || p.role || ')', ', ')
    INTO bad, who
    FROM public.profiles AS p
   WHERE p.role <> 'admin'
     AND p.role IS DISTINCT FROM COALESCE(
           (SELECT m.role FROM public.organization_members AS m
             WHERE m.user_id = p.id AND m.status = 'active'
             ORDER BY CASE m.role WHEN 'director' THEN 2 WHEN 'teacher' THEN 1 ELSE 0 END DESC
             LIMIT 1),
           'student');
  IF bad > 0 THEN
    RAISE EXCEPTION '% profile(s) would change role under the mirror: %', bad, who;
  END IF;
END
$$;

DROP TRIGGER IF EXISTS trg_organization_members_mirror_profile_role ON public.organization_members;
CREATE TRIGGER trg_organization_members_mirror_profile_role
  AFTER INSERT OR UPDATE OR DELETE ON public.organization_members
  FOR EACH ROW EXECUTE FUNCTION public.organization_members_mirror_profile_role();

COMMENT ON COLUMN public.profiles.organization_id IS
    'Deprecated 2026-10-03: membership lives in organization_members. Still '
    'written (when empty) by the phase-2 backend so the previous release keeps '
    'working on rollback; dropped in phase 4 of the same plan.';
COMMENT ON COLUMN public.profiles.role IS
    'The most this account may do anywhere: admin (platform staff, set only by '
    'the admin route) or the highest active organization_members.role, kept by '
    'mirror_profile_role(). Which organization: organization_members.';
