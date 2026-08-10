-- Grading redesign, Phase 1 / M6: the grade a certificate was issued on, kept
-- on the certificate. Design: grading-system-redesign.md (Accepted 2026-08-06),
-- Принцип 4 and D9.3.
--
-- Why a snapshot and not a join
-- =============================
-- A certificate is a document. Someone prints it, signs it, and a student puts
-- it in a folder for twenty years. Everything it was computed from is live and
-- editable: the course weights, the school's grade bands, the pass threshold,
-- the student's marks, even whether a piece of work was excused.
--
-- Recompute it on read and the paper in the folder stops matching the database
-- the first time a director nudges the band table — and it changes silently,
-- retroactively, for everyone who ever graduated. Grandfathering by
-- construction: what was true at issuance stays true, and a later edit is a
-- decision about the future only.
--
-- What is captured
-- ================
-- `grading_scheme` and `pass_threshold` — the rules in force, so a transcript
-- can render «4 (хорошо)» years after the school moved to letters.
--
-- `official_code` / `official_score` — the result itself, in whichever form the
-- scheme uses. Mutually exclusive, like `student_grades` (D7).
--
-- `graded_via` — how it was decided, which is the question a director asks when
-- two certificates from the same course disagree:
--   'computed'   — the weighted result stood;
--   'override'   — a teacher set it by hand;
--   'completion' — the course had nothing gradable, so completion was the
--                  result (the shape most of the existing certificates have).
--
-- Everything is nullable and nothing is backfilled. The certificates issued
-- before this migration were issued under rules nobody recorded, and inventing
-- a snapshot for them would be writing history rather than keeping it. NULL
-- reads as "issued before the platform kept this", which is the truth.

ALTER TABLE public.certificates
    ADD COLUMN grading_scheme TEXT,
    ADD COLUMN pass_threshold NUMERIC(5, 2),
    ADD COLUMN official_code TEXT,
    ADD COLUMN official_score NUMERIC(5, 2),
    ADD COLUMN graded_via TEXT;

-- The same "at most one of the two" rule the live grade obeys. Both at once was
-- never a state, only a mistake.
ALTER TABLE public.certificates
    ADD CONSTRAINT ck_certificates_one_official_grade
        CHECK ((CASE WHEN official_code IS NULL THEN 0 ELSE 1 END
              + CASE WHEN official_score IS NULL THEN 0 ELSE 1 END) <= 1);

ALTER TABLE public.certificates
    ADD CONSTRAINT ck_certificates_graded_via
        CHECK (graded_via IS NULL OR graded_via IN ('computed', 'override', 'completion'));
