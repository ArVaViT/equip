-- An invitation to a course points at a course that exists.
--
-- 20260912140000 declared `invitations.course_id ... REFERENCES
-- public.courses(id) ON DELETE CASCADE`, and supabase/schema.sql carries the
-- constraint as `invitations_course_id_fkey`. The production dump compared on
-- 2026-10-03 did not have it. Without it, deleting a course leaves its pending
-- invitations pointing nowhere: the letter still opens a preview of a course
-- that is gone.
--
-- Idempotent: a database that has the constraint is left alone. A database
-- that lacks it first loses the invitations that already point at nothing
-- (what ON DELETE CASCADE would have done at the time), then gets the
-- constraint. Everything runs in one transaction; ADD FOREIGN KEY briefly
-- locks writes to both `invitations` and `courses` — momentary at a few
-- hundred rows.

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
     WHERE conname = 'invitations_course_id_fkey'
       AND conrelid = 'public.invitations'::regclass
  ) THEN
    DELETE FROM public.invitations i
     WHERE i.course_id IS NOT NULL
       AND NOT EXISTS (SELECT 1 FROM public.courses c WHERE c.id = i.course_id);

    ALTER TABLE public.invitations
      ADD CONSTRAINT invitations_course_id_fkey
      FOREIGN KEY (course_id) REFERENCES public.courses(id) ON DELETE CASCADE;
  END IF;
END
$$;
