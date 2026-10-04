-- Membership decides what a policy shows.
--
-- Phase 3 of the memberships plan (20261003165050). Three SELECT policies
-- still answered "which organization is this person in" from
-- `profiles.organization_id`, through `current_organization_id()`, and one
-- of them answered "may they review" from the global `profiles.role`. Both
-- columns changed meaning in phase 1: the column is deprecated, and the role
-- is a mirror of the person's *highest* membership anywhere. A review on
-- 2026-10-03 drove that through the policies and found what it opens:
--
--   * a student of A who becomes a teacher of B mirrors `teacher`; the
--     certificates policy — column says A, role says teacher — then opened
--     every certificate of A to a person who is A's student;
--   * a member suspended in A kept reading A's closed courses and cohorts,
--     because the column still said A and the policies never asked the
--     membership whether it was active;
--   * `fulfil_pending_invitations`' 'organization' branch compared the column
--     and the global role, so a promotion in B closed a pending *teacher*
--     invitation into A for somebody who is still A's student — and the
--     'course' branch took a teacher of B for a teacher of A the same way.
--
-- Every one of those reads now asks `organization_members`, through the
-- helpers phase 1 installed: `is_member_of()`, `is_staff_of()`, and
-- `is_platform_staff()` for the platform. Nothing else changes shape: the
-- policies keep their names, the function keeps its signature, and the
-- backend of the previous release is not on any of these paths (it holds the
-- service-role key, which RLS does not see).

-- ---------------------------------------------------------------------
-- cohorts: staff of the organization, not everyone who sits in it
-- ---------------------------------------------------------------------
--
-- A cohort is a class list — dates, size, and through the junction the
-- people in it. The old policy let any *member* read it, because the column
-- had no role attached to the place. A student gets their own cohorts from
-- the API; by RLS they are the organization's staff's to see.

DROP POLICY IF EXISTS cohorts_select_own_organization ON public.cohorts;

CREATE POLICY cohorts_select_own_organization ON public.cohorts
    FOR SELECT TO authenticated
    USING (
        public.is_platform_staff()
        OR public.is_staff_of(organization_id)
    );

-- ---------------------------------------------------------------------
-- courses: a published `institute` course is its members' reading
-- ---------------------------------------------------------------------
--
-- Any active membership, in any role — the same rule the API applies
-- (`belongs_to`). A suspended membership is not one.

DROP POLICY IF EXISTS courses_select_published ON public.courses;

CREATE POLICY courses_select_published ON public.courses
    FOR SELECT TO authenticated
    USING (
        created_by = (SELECT auth.uid())
        OR public.is_platform_staff()
        OR (
            status = 'published'
            AND (
                access_mode = 'public'
                OR public.is_member_of(organization_id)
            )
        )
    );

-- ---------------------------------------------------------------------
-- certificates: your own, or your organization's as its staff
-- ---------------------------------------------------------------------
--
-- "Reviewer" used to be `profiles.role IN (teacher, director, admin)` next
-- to a column match — a role held anywhere opened the certificates of the
-- place the column named. It is now the role held *there*.

DROP POLICY IF EXISTS certificates_select_own_or_reviewer ON public.certificates;

CREATE POLICY certificates_select_own_or_reviewer ON public.certificates
    FOR SELECT TO authenticated
    USING (
        user_id = (SELECT auth.uid())
        OR public.is_platform_staff()
        OR public.is_staff_of(organization_id)
    );

-- ---------------------------------------------------------------------
-- fulfil_pending_invitations: "got what it offered" is read from the rows
-- ---------------------------------------------------------------------
--
-- Per scope, the person being the profile whose email matches:
--
--   platform      -- the person has an account. A platform invitation is
--                    an account and nothing else (2026-10-03: it no longer
--                    carries a role, see invitation_service), so the role
--                    offered on an older row is not a condition any more.
--   organization  -- an active membership of the inviting organization, in
--                    at least the offered role. A role held somewhere else
--                    is somewhere else.
--   course        -- enrolled on the course, solo or in any cohort, as
--                    before; and for a *teaching* role offered, held as
--                    staff of the course's organization. Membership is
--                    still not required for a student seat: somebody who
--                    joined a public course by themselves is on the course,
--                    and using the link afterwards still grants the
--                    membership (accept_invitation).
--
-- The rank order is the membership one — student < teacher < director — and
-- a role the function does not know never satisfies anything.

CREATE OR REPLACE FUNCTION public.fulfil_pending_invitations(p_profile_id uuid)
RETURNS integer
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
  closed integer;
BEGIN
  -- p_profile_id NULL means every profile: the backfill.
  UPDATE public.invitations AS i
  SET status = 'fulfilled',
      fulfilled_at = now()
  FROM public.profiles AS p
  WHERE i.status = 'pending'
    AND (p_profile_id IS NULL OR p.id = p_profile_id)
    AND lower(p.email) = lower(i.email)
    AND CASE i.scope
          WHEN 'platform' THEN true
          WHEN 'organization' THEN EXISTS (
            SELECT 1 FROM public.organization_members AS m
            WHERE m.user_id = p.id
              AND m.organization_id = i.organization_id
              AND m.status = 'active'
              AND (CASE m.role WHEN 'student' THEN 0 WHEN 'teacher' THEN 1 WHEN 'director' THEN 2 ELSE -1 END)
                  >= (CASE i.role WHEN 'student' THEN 0 WHEN 'teacher' THEN 1 WHEN 'director' THEN 2 ELSE 4 END)
          )
          WHEN 'course' THEN EXISTS (
            SELECT 1 FROM public.enrollments AS e
            WHERE e.user_id = p.id AND e.course_id = i.course_id
          ) AND (
            i.role = 'student'
            OR EXISTS (
              SELECT 1 FROM public.organization_members AS m
              WHERE m.user_id = p.id
                AND m.organization_id = i.organization_id
                AND m.status = 'active'
                AND (CASE m.role WHEN 'student' THEN 0 WHEN 'teacher' THEN 1 WHEN 'director' THEN 2 ELSE -1 END)
                    >= (CASE i.role WHEN 'student' THEN 0 WHEN 'teacher' THEN 1 WHEN 'director' THEN 2 ELSE 4 END)
            )
          )
          ELSE false
        END;
  GET DIAGNOSTICS closed = ROW_COUNT;
  RETURN closed;
END;
$$;

-- A membership written or raised is the fourth door a person arrives by.
-- The trigger function learns the table; the triggers it already serves
-- are untouched. The `profiles` trigger still fires on a role change, which
-- is now only the mirror echoing a membership write that already ran this
-- — harmless, and it goes with the column in phase 4.

CREATE OR REPLACE FUNCTION public.fulfil_invitations_after_change()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
  person uuid;
BEGIN
  IF TG_TABLE_NAME = 'enrollments' THEN
    PERFORM public.fulfil_pending_invitations(NEW.user_id);
  ELSIF TG_TABLE_NAME = 'organization_members' THEN
    PERFORM public.fulfil_pending_invitations(NEW.user_id);
  ELSIF TG_TABLE_NAME = 'profiles' THEN
    PERFORM public.fulfil_pending_invitations(NEW.id);
  ELSIF TG_TABLE_NAME = 'invitations' THEN
    -- An invitation written for somebody who is already there.
    FOR person IN
      SELECT p.id FROM public.profiles AS p WHERE lower(p.email) = lower(NEW.email)
    LOOP
      PERFORM public.fulfil_pending_invitations(person);
    END LOOP;
  END IF;
  RETURN NULL;
END;
$$;

-- Only an active row can fulfil anything; a suspension fires nothing.
DROP TRIGGER IF EXISTS trg_organization_members_fulfil_invitations ON public.organization_members;
CREATE TRIGGER trg_organization_members_fulfil_invitations
  AFTER INSERT OR UPDATE ON public.organization_members
  FOR EACH ROW
  WHEN (NEW.status = 'active')
  EXECUTE FUNCTION public.fulfil_invitations_after_change();

-- One run for everybody. The phase-1 backfill made the column and the
-- memberships agree, so no organization invitation changes its answer here;
-- what this closes is a platform invitation to somebody who already has an
-- account, which the old role condition could still hold open.
SELECT public.fulfil_pending_invitations(NULL);

-- ---------------------------------------------------------------------
-- The column's last reader goes
-- ---------------------------------------------------------------------
--
-- Nothing references `current_organization_id()` once the three policies
-- above are in place (the storage policies use can_teach() and
-- is_platform_staff()). Kept, it would be a helper that reads a deprecated
-- column and answers the wrong question with a plausible uuid — the next
-- policy written by habit would use it. The plan had it going with the
-- column in phase 4; nothing is gained by waiting.

DROP FUNCTION IF EXISTS public.current_organization_id();
