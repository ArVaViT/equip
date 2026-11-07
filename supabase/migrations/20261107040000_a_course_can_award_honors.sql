-- A course can award «with honors» (с отличием), and a certificate keeps it.
--
-- Grading redesign, Phase 3 (grading-system-redesign.md, Q3 answered
-- 2026-08-06: yes, a teacher's switch, off by default). When it is on, a
-- student whose official grade is in the top band of the course's scheme
-- (A in letter, 5 in five-point) gets «with honors» on the certificate and
-- on the transcript line. Schemes without bands (pass_fail, percent) never
-- earn it, and the switch is not offered for them.
--
-- `courses.with_honors` -- the switch. NOT NULL DEFAULT false: every
-- existing course stays exactly as it was.
--
-- `certificates.with_honors` -- decided once, at approval, and frozen like
-- the grade (M6, 20260810120000): a teacher who turns honors off next year
-- does not take it back from anyone. DEFAULT false: no certificate issued
-- so far was issued with honors, which is the truth.
--
-- `certificates.academic_hours` -- the hours the course carried when the
-- certificate was issued, so the transcript prints them from the document
-- rather than from a course that may since have been edited. NULL on every
-- certificate issued before this: nobody recorded them.
--
-- Only additions. The backend that runs today never reads the new columns,
-- and every one has a default or is nullable, so its INSERTs keep working.
-- Idempotent: IF NOT EXISTS / DROP ... IF EXISTS throughout.

ALTER TABLE public.courses
  ADD COLUMN IF NOT EXISTS with_honors boolean DEFAULT false NOT NULL;

ALTER TABLE public.certificates
  ADD COLUMN IF NOT EXISTS with_honors boolean DEFAULT false NOT NULL,
  ADD COLUMN IF NOT EXISTS academic_hours integer;

ALTER TABLE public.certificates
  DROP CONSTRAINT IF EXISTS certificates_academic_hours_check;
ALTER TABLE public.certificates
  ADD CONSTRAINT certificates_academic_hours_check CHECK (academic_hours > 0);

COMMENT ON COLUMN public.courses.with_honors IS
  'Teacher switch: a top-band official grade earns «with honors» on the certificate. Ignored for pass_fail and percent. See 20261107040000.';
COMMENT ON COLUMN public.certificates.with_honors IS
  'Frozen at approval: the course offered honors and the official grade was in the top band. Never recomputed. See 20261107040000.';
