-- Grading redesign, Phase 1 / M4: «освобождение» — excusing a student from a
-- piece of work. Design: grading-system-redesign.md (Accepted 2026-08-06), D6.
--
-- Why it has to touch two denominators
-- ====================================
-- Mercy that only removes the item from the *grade* is not mercy. The student
-- excused from an assignment still has an incomplete chapter, so progress
-- never reaches 100, so the certificate gate is permanently unsatisfiable —
-- for exactly the sick teenager or the late-joining adult the feature exists
-- to help. The design calls this out as a blocker, twice.
--
-- So an exemption removes the item from both numerators and both denominators:
-- the grade (Canvas `EX` semantics) and the progress. Creating one atomically
-- marks the item's chapter complete with `completion_type = 'excused'` and
-- resyncs the enrolment; deleting one reverts only the rows it created.
--
-- Why the chapter, not just the item
-- ==================================
-- Progress is counted over gradable *chapters*, so an excused item has to
-- reach that layer or the two systems disagree. `'excused'` is a distinct
-- completion type rather than reusing `'teacher'` precisely so the inverse can
-- tell apart "the teacher marked this done" from "this was waived" and revert
-- only the latter.
--
-- The student-facing state is «освобождено», never «не сдано» — the work was
-- not missed, it was set aside by a teacher who wrote down why.

CREATE TABLE public.grade_exemptions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    student_id UUID NOT NULL,
    course_id TEXT NOT NULL REFERENCES public.courses(id) ON DELETE CASCADE,
    item_type TEXT NOT NULL CHECK (item_type IN ('quiz', 'assignment')),
    item_id UUID NOT NULL,
    -- Optional, and visible to directors: waiving work is a decision someone
    -- will be asked about, particularly when it is the last thing between a
    -- student and a certificate.
    reason TEXT,
    created_by UUID REFERENCES public.profiles(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- One exemption per student per item. A second attempt to waive the same
    -- work is a no-op, not a duplicate row that the inverse would half-revert.
    UNIQUE (student_id, item_type, item_id)
);

-- "Which items has this student been excused from" — the question every grade
-- calculation asks, once per student per course.
CREATE INDEX ix_grade_exemptions_student_course ON public.grade_exemptions (student_id, course_id);

-- No direct client access. An exemption changes a student's official result;
-- with the anon key in the browser, grants are the boundary.
REVOKE ALL ON public.grade_exemptions FROM anon, authenticated;
ALTER TABLE public.grade_exemptions ENABLE ROW LEVEL SECURITY;

-- `'excused'` joins the completion vocabulary. Kept distinct from `'teacher'`
-- so removing an exemption reverts exactly what it created and leaves a
-- teacher's own manual completion alone.
ALTER TABLE public.chapter_progress
    DROP CONSTRAINT IF EXISTS chapter_progress_completion_type_check;

ALTER TABLE public.chapter_progress
    ADD CONSTRAINT chapter_progress_completion_type_check
        CHECK (completion_type IN ('self', 'teacher', 'quiz', 'excused'));
