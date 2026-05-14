-- Tech-debt sweep follow-up to the 2026-05-14 DB audit. Two clusters:
--
-- 1. Drop 4 redundant left-prefix indexes — each is fully covered by
--    an existing composite. Saves write overhead on inserts/updates.
--    (Companion to 20260513195434_perf_indexes_and_autovacuum which
--    dropped the first 3 such cases.)
--
-- 2. Fix referential integrity on user-delete paths. Four FKs against
--    auth.users had the wrong ON DELETE rule for an LMS audit trail:
--
--    HIGH   - student_grades.graded_by_fkey was ON DELETE CASCADE,
--             meaning deleting a teacher silently wiped every grade
--             they ever issued. Change to ON DELETE SET NULL so the
--             grade row survives with a null grader reference. The
--             column needs to be made nullable for this.
--
--    MEDIUM - assignment_submissions.graded_by_fkey
--             certificates.teacher_approved_by_fkey
--             certificates.admin_approved_by_fkey
--             …all had NO ACTION (the default), which means deleting
--             a teacher fails with an FK violation. Same fix: ON
--             DELETE SET NULL. Columns are already nullable.


-- 1. Redundant indexes ---------------------------------------------------
DROP INDEX IF EXISTS public.idx_submissions_assignment_id;       -- covered by assignment_submissions_assignment_id_student_id_key
DROP INDEX IF EXISTS public.ix_content_translations_entity;      -- covered by content_translations_unique
DROP INDEX IF EXISTS public.ix_notifications_user_id;            -- covered by ix_notifications_user_id_is_read
DROP INDEX IF EXISTS public.idx_student_grades_student_id;       -- covered by student_grades_student_id_course_id_key


-- 2. Fix user-delete FK behaviour ---------------------------------------

-- 2a. student_grades.graded_by: allow NULL, switch CASCADE → SET NULL
ALTER TABLE public.student_grades
  ALTER COLUMN graded_by DROP NOT NULL;

ALTER TABLE public.student_grades
  DROP CONSTRAINT IF EXISTS student_grades_graded_by_fkey;

ALTER TABLE public.student_grades
  ADD CONSTRAINT student_grades_graded_by_fkey
    FOREIGN KEY (graded_by) REFERENCES auth.users(id) ON DELETE SET NULL;


-- 2b. assignment_submissions.graded_by: NO ACTION → SET NULL
ALTER TABLE public.assignment_submissions
  DROP CONSTRAINT IF EXISTS assignment_submissions_graded_by_fkey;

ALTER TABLE public.assignment_submissions
  ADD CONSTRAINT assignment_submissions_graded_by_fkey
    FOREIGN KEY (graded_by) REFERENCES auth.users(id) ON DELETE SET NULL;


-- 2c. certificates.teacher_approved_by: NO ACTION → SET NULL
ALTER TABLE public.certificates
  DROP CONSTRAINT IF EXISTS certificates_teacher_approved_by_fkey;

ALTER TABLE public.certificates
  ADD CONSTRAINT certificates_teacher_approved_by_fkey
    FOREIGN KEY (teacher_approved_by) REFERENCES auth.users(id) ON DELETE SET NULL;


-- 2d. certificates.admin_approved_by: NO ACTION → SET NULL
ALTER TABLE public.certificates
  DROP CONSTRAINT IF EXISTS certificates_admin_approved_by_fkey;

ALTER TABLE public.certificates
  ADD CONSTRAINT certificates_admin_approved_by_fkey
    FOREIGN KEY (admin_approved_by) REFERENCES auth.users(id) ON DELETE SET NULL;
