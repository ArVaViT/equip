-- Rubrics: the same standard applied to the twentieth essay as to the first.
-- Design: assessment-integrity-and-the-graders-day.md, §6.3.
--
-- Why a rubric, and why it is not about speed
-- ==========================================
-- Equip marks an essay today with a number and a comment box. Every serious
-- platform in this space is rubric-first, and the reason is consistency rather
-- than speed: a rubric is what makes the mark on the twentieth essay the same
-- judgement as the mark on the first, and it is the only answer a school has
-- when a student asks why they got 70 and their friend got 85.
--
-- It is also the answer to a criticism the platform cannot otherwise meet. A
-- grade that is one person's impression is unfalsifiable; a grade that is four
-- named criteria with a level chosen on each can be discussed, appealed, and
-- defended. For a school whose documents are meant to be taken seriously, that
-- is the difference between a mark and an opinion.
--
-- The decision recorded is the level, not the number
-- =================================================
-- `rubric_marks` stores which level the teacher chose. The points come from
-- the level. That ordering is deliberate: a school that decides «уровень
-- «хорошо» стоит 8, а не 7» edits the level once, and every mark that rests on
-- it follows — which is how a rubric edited mid-marking can be applied to work
-- already marked (Gradescope's best idea) instead of forcing a teacher to
-- reopen finished essays by hand.
--
-- The corollary is that levels are deactivated, never deleted. A deleted level
-- turns every mark that referenced it into a mark by nobody, for nothing.
--
-- Course-scoped, and reusable inside the course
-- ============================================
-- A rubric belongs to a course and can be attached to several assignments in
-- it — «наша стандартная рубрика эссе» is a real thing a school wants. It
-- travels with the course when the course is cloned, exactly as the rest of
-- the grading configuration does (D13). When organizations land, an org-level
-- rubric library is an additive change to this shape rather than a rewrite:
-- the course_id becomes nullable and an org_id joins it.

CREATE TABLE public.rubrics (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    course_id text NOT NULL REFERENCES public.courses(id) ON DELETE CASCADE,
    title text NOT NULL,
    created_by uuid REFERENCES public.profiles(id) ON DELETE SET NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    -- Deactivated rather than deleted, for the same reason levels are: a
    -- rubric referenced by a mark on a closed ведомость has to stay readable.
    archived_at timestamptz
);

CREATE INDEX ix_rubrics_course ON public.rubrics (course_id);

CREATE TABLE public.rubric_criteria (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    rubric_id uuid NOT NULL REFERENCES public.rubrics(id) ON DELETE CASCADE,
    order_index integer NOT NULL DEFAULT 0,
    title text NOT NULL,
    description text,
    archived_at timestamptz
);

CREATE INDEX ix_rubric_criteria_rubric ON public.rubric_criteria (rubric_id, order_index);

CREATE TABLE public.rubric_levels (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    criterion_id uuid NOT NULL REFERENCES public.rubric_criteria(id) ON DELETE CASCADE,
    order_index integer NOT NULL DEFAULT 0,
    label text NOT NULL,
    -- Points are on the level because the level is what the teacher picks.
    -- Non-negative and bounded so a typo cannot produce a 5000-point criterion
    -- that silently swamps every other one.
    points integer NOT NULL DEFAULT 0,
    description text,
    archived_at timestamptz,
    CONSTRAINT rubric_levels_points_range CHECK (points >= 0 AND points <= 1000)
);

CREATE INDEX ix_rubric_levels_criterion ON public.rubric_levels (criterion_id, order_index);

-- One rubric per assignment. Two would mean two totals and no answer to which
-- one the grade came from.
CREATE TABLE public.assignment_rubrics (
    assignment_id uuid PRIMARY KEY REFERENCES public.assignments(id) ON DELETE CASCADE,
    rubric_id uuid NOT NULL REFERENCES public.rubrics(id) ON DELETE CASCADE,
    attached_at timestamptz NOT NULL DEFAULT now(),
    attached_by uuid REFERENCES public.profiles(id) ON DELETE SET NULL
);

CREATE INDEX ix_assignment_rubrics_rubric ON public.assignment_rubrics (rubric_id);

-- What the teacher decided, one row per criterion per submission.
CREATE TABLE public.rubric_marks (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    submission_id uuid NOT NULL REFERENCES public.assignment_submissions(id) ON DELETE CASCADE,
    criterion_id uuid NOT NULL REFERENCES public.rubric_criteria(id) ON DELETE CASCADE,
    level_id uuid NOT NULL REFERENCES public.rubric_levels(id) ON DELETE RESTRICT,
    -- The teacher's note on this criterion specifically. Optional, and separate
    -- from the feedback on the whole piece of work.
    comment text,
    marked_by uuid REFERENCES public.profiles(id) ON DELETE SET NULL,
    marked_at timestamptz NOT NULL DEFAULT now(),
    -- One decision per criterion per submission. A second row would mean the
    -- same criterion marked twice with no way to know which one counted.
    CONSTRAINT uq_rubric_marks_submission_criterion UNIQUE (submission_id, criterion_id)
);

CREATE INDEX ix_rubric_marks_submission ON public.rubric_marks (submission_id);

COMMENT ON TABLE public.rubrics IS
    'Named marking standard for a course. §6.3 of assessment-integrity-and-the-graders-day.md';
COMMENT ON COLUMN public.rubric_marks.level_id IS
    'The decision. Points are read from the level, so a level edited later carries through to marks already made.';
COMMENT ON COLUMN public.rubric_levels.points IS
    'Points for this level. Edited in one place; every mark resting on it follows.';
