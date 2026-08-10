-- Correction to M4 (20260810024850), found by adversarial review before the
-- feature reached anyone.
--
-- `item_id` is polymorphic — a quiz or an assignment — so it carries no foreign
-- key, and quizzes and assignments are hard-deleted. That left one state with
-- no way out:
--
--   1. a teacher excuses a student from an assignment; the chapter is marked
--      complete as 'excused' and the enrolment's progress rises;
--   2. the assignment is deleted from the course;
--   3. the teacher removes the exemption — but the service reaches the chapter
--      *through the item*, which no longer exists, so the revert is skipped
--      while the exemption row is deleted anyway.
--
-- The chapter is now completed as 'excused' with no exemption behind it, the
-- progress still counts it toward the certificate gate, and the guard on
-- `PUT .../incomplete` refuses to undo it — pointing the teacher at a row that
-- is gone. Unreachable by every API path.
--
-- The exemption should never have needed the item to find its own chapter. It
-- is recorded here directly, with a real foreign key: deleting the chapter now
-- takes its exemptions with it, and deleting only the item leaves a row that
-- can still be removed cleanly.

ALTER TABLE public.grade_exemptions
    ADD COLUMN chapter_id TEXT REFERENCES public.chapters(id) ON DELETE CASCADE;

-- Backfill by the same route the service used to take. The table is empty in
-- production (the feature has not shipped), so this is for parity with any
-- environment that has been experimenting.
UPDATE public.grade_exemptions e
SET chapter_id = q.chapter_id
FROM public.quizzes q
WHERE e.item_type = 'quiz' AND e.item_id = q.id;

UPDATE public.grade_exemptions e
SET chapter_id = a.chapter_id
FROM public.assignments a
WHERE e.item_type = 'assignment' AND e.item_id = a.id;

-- Any row that could not be resolved refers to an item that is already gone —
-- exactly the state above. There are none in production; deleting them here
-- keeps the NOT NULL below honest rather than inventing a chapter for them.
DELETE FROM public.grade_exemptions WHERE chapter_id IS NULL;

ALTER TABLE public.grade_exemptions
    ALTER COLUMN chapter_id SET NOT NULL;

-- "Which chapters is this student excused in" is asked once per chapter write.
CREATE INDEX ix_grade_exemptions_chapter ON public.grade_exemptions (student_id, chapter_id);
