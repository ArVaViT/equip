-- The rest of the ведомость's letterhead, frozen with the rest of it.
--
-- The document already keeps its own grades, names, поток and language. These
-- are the remaining fields the printed page carries, and every one of them is
-- editable in a live table:
--
--   school name and city   — `org_settings`, a school can rename itself;
--   teacher               — a profile, and people change their names and leave;
--   academic hours        — `courses.academic_hours`, edited when a course is
--                           restructured;
--   поток dates           — `cohorts`, adjustable while a term runs.
--
-- Read live, any of them silently rewrites the letterhead of every document
-- already signed and filed. A ведомость from 2024 would start claiming this
-- year's course length under next year's school name — which is exactly the
-- failure the snapshot exists to prevent, one line higher up the page.
--
-- Nullable throughout: a school that has not filled in its name yet prints a
-- document without one, which is honest. Inventing a placeholder would put
-- words on a page somebody signs.

ALTER TABLE public.grade_sheets
    ADD COLUMN school_name TEXT,
    ADD COLUMN school_city TEXT,
    ADD COLUMN teacher_name TEXT,
    ADD COLUMN academic_hours INTEGER,
    ADD COLUMN cohort_start TIMESTAMPTZ,
    ADD COLUMN cohort_end TIMESTAMPTZ;
