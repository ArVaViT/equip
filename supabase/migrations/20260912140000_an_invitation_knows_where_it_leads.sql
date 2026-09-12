-- An invitation knows where it leads.
--
-- Until now an invitation carried an organization and a role, and that
-- was the whole of it. The first live course needed to invite five
-- people onto one course, which the table could not say, and accepting
-- did not put anybody in the organization either (fixed in the service
-- alongside this migration).
--
-- `scope` is a column rather than something inferred from which fields
-- are null. A course invitation whose course was deleted has to stay a
-- course invitation that fails loudly; inferring scope from `course_id
-- IS NULL` would quietly turn it into an organization invitation and
-- hand somebody a membership they were never offered.
--
--   platform      -- an account, nothing more. No organization, no course.
--   organization  -- membership + role. What every existing row is.
--   course        -- membership + role + enrolment on `course_id`.
--
-- Existing rows are organization invitations by definition: the column
-- was NOT NULL before this and every row has one.

ALTER TABLE public.invitations
  ADD COLUMN scope text NOT NULL DEFAULT 'organization',
  ADD COLUMN course_id character varying REFERENCES public.courses(id) ON DELETE CASCADE;

ALTER TABLE public.invitations
  ADD CONSTRAINT chk_invitations_scope
    CHECK (scope IN ('platform', 'organization', 'course'));

-- The scope and its target agree, in both directions. A course scope
-- without a course is an invitation that cannot be honoured; a course
-- on any other scope is a promise nothing reads.
ALTER TABLE public.invitations
  ADD CONSTRAINT chk_invitations_course_matches_scope
    CHECK (
      (scope = 'course' AND course_id IS NOT NULL)
      OR (scope <> 'course' AND course_id IS NULL)
    );

CREATE INDEX ix_invitations_course_id ON public.invitations (course_id)
  WHERE course_id IS NOT NULL;

-- The uniqueness key gains the organization and the course.
--
-- It was `(email, role) WHERE status='pending'` — global. Two schools
-- shared one namespace: the second one to invite a person got the
-- first one's row back from the service's lookup and mailed out the
-- first one's token. One school inviting the same person to two
-- courses hit the same wall from the other side.
--
-- `coalesce(course_id, '')` because NULLs do not collide in a unique
-- index, and two pending organization invitations for the same person
-- must collide — that is the deduplication the index is there to do.
DROP INDEX IF EXISTS ix_invitations_one_pending_per_email_role;

CREATE UNIQUE INDEX ix_invitations_one_pending_per_scope
  ON public.invitations (organization_id, email, role, coalesce(course_id, ''))
  WHERE status = 'pending';

COMMENT ON COLUMN public.invitations.scope IS
  'What accepting this invitation grants: platform (an account), '
  'organization (membership + role), course (membership + role + '
  'enrolment). Stored rather than inferred so a course invitation whose '
  'course is gone fails loudly instead of degrading into a different '
  'kind of invitation.';

COMMENT ON COLUMN public.invitations.course_id IS
  'The course an accepted invitation enrols into. Required when scope = '
  'course, forbidden otherwise (chk_invitations_course_matches_scope). '
  'ON DELETE CASCADE: an invitation to a deleted course leads nowhere, '
  'and a dangling row would answer the preview route with a course that '
  'no longer exists.';
