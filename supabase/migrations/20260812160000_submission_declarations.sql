-- What a student says about their own work, at the moment they hand it in.
-- Design: assessment-integrity-and-the-graders-day.md, §4.
--
-- Why not detection
-- =================
-- AI detectors do not work. They false-positive on writers whose English is a
-- second language — which is most of this school — and false-negative on
-- anything lightly edited. A platform that renders «87% AI» has manufactured
-- an accusation it cannot support, against exactly the students least able to
-- argue back. Nothing here detects anything.
--
-- What the evidence does support
-- ==============================
-- A 2023 double-blind randomised field study of unproctored online exams —
-- this school's exact setting — found that a reminder before the exam reduced
-- cheating, and that the effective reminder carried three things together: the
-- policy, an example of what integrity means here, and the consequences. That
-- is what `courses.ai_policy` plus this table put on the screen, before the
-- work is submitted rather than after.
--
-- (The famous «sign at the top rather than the bottom» result is not the basis
-- for any of this: the original authors published six failed replications in
-- 2020 and the data was later shown to be fabricated.)
--
-- Honesty is never punished harder than concealment
-- =================================================
-- A student who declares they used AI where the course forbids it is telling
-- the truth about a rule they broke. The submission is accepted and the
-- declaration recorded, and the teacher sees it — because refusing it at the
-- door teaches the next student to tick the other box. What follows is a
-- conversation, which is what an integrity process is.

ALTER TABLE public.courses
    ADD COLUMN ai_policy text NOT NULL DEFAULT 'ai_with_disclosure';

ALTER TABLE public.courses
    ADD CONSTRAINT courses_ai_policy_check
    CHECK (ai_policy IN ('ai_forbidden', 'ai_with_disclosure', 'ai_open'));

COMMENT ON COLUMN public.courses.ai_policy IS
    'What a student may use. Default is disclosure rather than a ban: an unenforceable ban is broken silently and teaches concealment.';

CREATE TABLE public.submission_declarations (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    submission_id uuid NOT NULL REFERENCES public.assignment_submissions(id) ON DELETE CASCADE,
    -- The policy as it stood when this was signed, not a pointer to a row a
    -- teacher can edit afterwards. Same principle as the ведомость and the
    -- certificate: what somebody agreed to has to survive the thing they
    -- agreed to being changed.
    policy text NOT NULL,
    statement text NOT NULL,
    -- `none` or `assisted`. Under a ban, `assisted` is a disclosed breach —
    -- recorded, shown to the teacher, and never grounds for the platform to
    -- refuse the work by itself.
    ai_use text NOT NULL,
    accepted_at timestamptz NOT NULL DEFAULT now(),
    ip text,
    CONSTRAINT submission_declarations_ai_use_check CHECK (ai_use IN ('none', 'assisted')),
    CONSTRAINT submission_declarations_policy_check
        CHECK (policy IN ('ai_forbidden', 'ai_with_disclosure', 'ai_open')),
    -- One declaration per submission. A second would leave two answers to
    -- «what did they say about this work».
    CONSTRAINT uq_submission_declarations_submission UNIQUE (submission_id)
);

CREATE INDEX ix_submission_declarations_submission ON public.submission_declarations (submission_id);

COMMENT ON TABLE public.submission_declarations IS
    'What the student said about this specific piece of work, with the policy text they were shown. §4 of assessment-integrity-and-the-graders-day.md';
COMMENT ON COLUMN public.submission_declarations.statement IS
    'The text as displayed. A pointer to an editable row would prove nothing later.';
