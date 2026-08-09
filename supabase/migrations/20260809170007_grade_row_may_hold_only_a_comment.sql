-- Correction to M3 (20260809160626), found by adversarial review before the
-- feature reached anyone.
--
-- The original CHECK demanded exactly one override per row. That made a row
-- holding only a teacher's comment illegal — and a comment without a grade is
-- an ordinary thing to write: "good progress, resubmit section 3". Worse, it
-- forced clearing a grade to delete the whole row, taking the comment with it.
--
-- The gradebook's empty grade field then meant "delete this row", so a teacher
-- editing a comment on a student whose numeric override the screen could not
-- display would silently destroy both.
--
-- At most one override, then. A row may hold:
--
--   a symbol            — the hand-set grade for symbol schemes;
--   a number            — the hand-set grade for percent courses;
--   neither             — the teacher wrote a comment and left the grade alone.
--
-- Both at once stays impossible: that was never a state, only a mistake.
-- Clearing a grade now empties the override and keeps the comment; the row is
-- deleted only when nothing at all is left on it.

ALTER TABLE public.student_grades
    DROP CONSTRAINT ck_student_grades_one_override;

ALTER TABLE public.student_grades
    ADD CONSTRAINT ck_student_grades_one_override
        CHECK ((CASE WHEN override_code IS NULL THEN 0 ELSE 1 END + CASE WHEN override_score IS NULL THEN 0 ELSE 1 END) <= 1);
