-- Grading redesign, Phase 1 / M3: the manual grade becomes a typed override.
-- Design: grading-system-redesign.md (Accepted 2026-08-06), decision D7.
--
-- What was wrong
-- ==============
-- `student_grades.grade` was a free-text VARCHAR(10) with no validation and no
-- history. Three consequences, all of them about trust rather than tidiness:
--
-- 1. Unrepresentable values were representable. "Aa+" fits. «удовлетворительно»
--    does not fit in ten characters, so a Russian-language school could not
--    even write its own grade correctly.
-- 2. The computed grade was nowhere. A teacher overriding 64% with a "C" left
--    no trace of what the system had calculated, so nobody could later see
--    that a mark had been moved, let alone by how much.
-- 3. No reason, no history. Who set it survived only as the *last* writer:
--    `graded_by` is overwritten on every edit, so the person who first set a
--    grade disappears the moment anyone touches it.
--
-- What lands
-- ==========
-- Two mutually exclusive columns hold the override:
--
--   override_code   — a symbol from the course's scheme ('pass'/'fail',
--                     '5'..'2', 'A'..'F'). Canonical codes, never localized
--                     display text: the display layer maps them to «зачёт» or
--                     «4 (хорошо)» per locale.
--   override_score  — a percentage, for the `percent` scheme where the number
--                     is the result.
--
-- The CHECK makes "both" and "neither" impossible. A row exists
-- only to express an override, so clearing one is a DELETE, not an UPDATE to
-- NULL — otherwise the CHECK would forbid the very state "cleared".
--
-- `computed_score` snapshots what the calculator said at the moment of the
-- override, so every surface can show both numbers side by side and a director
-- can see a hand-set grade for what it is.
--
-- `reason` is optional. Making it mandatory would tax the common, kind case —
-- a teacher correcting an obvious miscount — and D7 deliberately leaves
-- accountability to the audit trail and the override glyph instead.
--
-- Safety
-- ======
-- `student_grades` has 0 rows in production (verified immediately before this
-- migration), so dropping the free-text column loses nothing. The window for
-- reshaping this table without a data migration closes the moment a school
-- issues its first hand-set grade.

ALTER TABLE public.student_grades
    ADD COLUMN override_code TEXT
        CHECK (override_code IN ('pass', 'fail', '5', '4', '3', '2', 'A', 'B', 'C', 'D', 'F')),
    ADD COLUMN override_score NUMERIC(5, 2)
        CHECK (override_score >= 0 AND override_score <= 100),
    ADD COLUMN computed_score NUMERIC(5, 2),
    ADD COLUMN reason TEXT;

-- Exactly one form of override per row: a symbol or a number, never both and
-- never neither. "Neither" is what a cleared override would look like, and a
-- cleared override is an absent row.
ALTER TABLE public.student_grades
    ADD CONSTRAINT ck_student_grades_one_override
        -- Spelled with CASE rather than num_nonnulls so the identical text
        -- works in SQLite, which is what the test suite builds from the models.
        CHECK ((CASE WHEN override_code IS NULL THEN 0 ELSE 1 END + CASE WHEN override_score IS NULL THEN 0 ELSE 1 END) = 1);

-- The free-text grade is gone. Nothing read it for display — the gradebook
-- renders the calculated symbol — and nothing wrote a validated value into it.
ALTER TABLE public.student_grades
    DROP COLUMN grade;
