-- Grading redesign, Phase 2 / M5: «закрытие ведомости» — the frozen document.
-- Design: grading-system-redesign.md (Accepted 2026-08-06), D11 and Принцип 4.
--
-- A report is live; a document is not
-- ===================================
-- The ведомость is what a director signs and files. Everything it is computed
-- from stays editable afterwards: a teacher can re-mark an essay, lift an
-- exemption, or hand-set a grade months later, and a report rendered from live
-- data would change in the filing cabinet. Closing it takes a snapshot; the
-- printable renders from that snapshot and never from the live tables.
--
-- Same reasoning as the certificate snapshot one migration earlier, applied to
-- the other signed artifact. The two must age the same way.
--
-- Why cohort-scoped from the first day
-- ====================================
-- Not deferred: the moment a school runs the same course a second year, an
-- unscoped ведомость mixes two поток in one signed document, and there is no
-- way to tell afterwards which student belonged to which. `cohort_id IS NULL`
-- means «без потока» — a real bucket for solo students, not an absence.
--
-- Reopening, rather than editing
-- ==============================
-- A closed sheet cannot be quietly corrected. Reopening is explicit, carries a
-- reason, and is audited; re-closing supersedes the old sheet instead of
-- overwriting it, so the history of what was signed survives. The printable
-- carries a «была переоткрыта» mark, because a document that changed after
-- signature must say so on its face.

CREATE TABLE public.grade_sheets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    course_id TEXT NOT NULL REFERENCES public.courses(id) ON DELETE CASCADE,
    -- NULL is «без потока», a bucket rather than a missing value — which is
    -- exactly why this is RESTRICT and not SET NULL. Nulling the column on a
    -- signed sheet does not "forget the cohort", it silently moves the
    -- document into the «без потока» bucket, where it shadows that bucket's own
    -- page and collides with the unique index below. A поток with a signed
    -- ведомость is not deletable, and should not be.
    cohort_id UUID REFERENCES public.cohorts(id) ON DELETE RESTRICT,
    -- The поток's name as it was, so the printed page keeps its heading even
    -- if the cohort is renamed afterwards.
    cohort_name TEXT,

    -- The rules in force at closing. A school that moves its scale later must
    -- not move what this document says it certified.
    grading_scheme TEXT NOT NULL,
    pass_threshold NUMERIC(5, 2),

    finalized_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finalized_by UUID REFERENCES public.profiles(id) ON DELETE SET NULL,
    reopened_at TIMESTAMPTZ,
    reopened_by UUID REFERENCES public.profiles(id) ON DELETE SET NULL,
    reopen_reason TEXT,
    -- Set when a later closing replaces this one. The old sheet is kept.
    superseded_at TIMESTAMPTZ,
    -- The «была переоткрыта» mark, carried onto the document that replaced a
    -- reopened one. Stamping only the superseded page marks the copy nobody
    -- prints again.
    corrects_sheet_id UUID REFERENCES public.grade_sheets(id) ON DELETE SET NULL,
    correction_reason TEXT,

    -- A sheet cannot have been reopened before it was closed, and a reopening
    -- without a reason is the thing the reason exists to prevent.
    CONSTRAINT ck_grade_sheets_reopen_is_deliberate
        CHECK (reopened_at IS NULL OR (reopened_at >= finalized_at AND reopen_reason IS NOT NULL))
);

-- One open sheet per поток. `COALESCE` because NULL is a real bucket here and
-- a plain unique index would let «без потока» be closed any number of times.
CREATE UNIQUE INDEX uq_grade_sheets_active ON public.grade_sheets
    (course_id, COALESCE(cohort_id, '00000000-0000-0000-0000-000000000000'::uuid))
    WHERE superseded_at IS NULL;

CREATE INDEX ix_grade_sheets_course ON public.grade_sheets (course_id);

CREATE TABLE public.grade_sheet_rows (
    sheet_id UUID NOT NULL REFERENCES public.grade_sheets(id) ON DELETE CASCADE,
    student_id UUID NOT NULL,

    -- A result, not a computation state. The calculator's vocabulary answers
    -- "why is there no number"; a signed document answers "what did this
    -- person get", and those are different questions:
    --   'pass' / 'fail'      — measured against the pass line in force;
    --   'completion_pass'    — the course had nothing gradable in it;
    --   'not_attested'       — «не аттестован»: every item excused, so there
    --                          was nothing to assess and a person had to say so.
    result_state TEXT NOT NULL
        CHECK (result_state IN ('pass', 'fail', 'completion_pass', 'not_attested')),
    official_code TEXT,
    official_score NUMERIC(5, 2),
    -- The director-visible glyph: this grade was set by hand, not computed.
    -- A signing director should see that at a glance rather than have to ask.
    is_override BOOLEAN NOT NULL DEFAULT FALSE,

    PRIMARY KEY (sheet_id, student_id),

    -- At most one of the two, exactly as `student_grades` and `certificates`
    -- already have it. Written with CASE rather than `num_nonnulls` so SQLite
    -- can materialise it for the test suite.
    CONSTRAINT ck_grade_sheet_rows_one_grade
        CHECK ((CASE WHEN official_code IS NULL THEN 0 ELSE 1 END
              + CASE WHEN official_score IS NULL THEN 0 ELSE 1 END) <= 1)
);

-- Backend-only, like every table that decides an official result. With the
-- anon key in the browser, grants are the boundary — and a student who could
-- INSERT here would be writing their own line in a signed document.
REVOKE ALL ON public.grade_sheets FROM anon, authenticated;
REVOKE ALL ON public.grade_sheet_rows FROM anon, authenticated;
ALTER TABLE public.grade_sheets ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.grade_sheet_rows ENABLE ROW LEVEL SECURITY;
