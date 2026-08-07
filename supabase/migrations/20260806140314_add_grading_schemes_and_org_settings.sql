-- Grading redesign, Phase 1 / M1: per-course grading scheme + institutional
-- settings. Design: equipbible-docs/product/decisions/grading-system-redesign.md
-- (Accepted 2026-08-06), decisions D1, D3 and D8.
--
-- Context
-- =======
-- Until now a course had no notion of *how* it is graded: grade_calculator.py
-- hardcoded US letter bands 90/80/70/60 for every course on the platform, and
-- there was no course-level line separating "passed" from "failed" at all --
-- certificates gated on progress == 100 only.
--
-- This migration adds the two columns the whole redesign hangs off:
--
--   courses.grading_scheme  -- one of four presets, never free-form
--   courses.pass_threshold  -- the course-result line for band schemes
--
-- plus academic_hours, which the ведомость and the transcript print as
-- «объём в часах» (nullable: most courses will not set it).
--
-- Why presets and not configurable categories: the anti-model here is Moodle,
-- whose aggregation pickers and per-item weights are documented on its own
-- forums as silently corrupting totals for non-technical teachers. Teachers
-- pick a preset; only the institution configures bands (see org_settings).
--
-- Institutional default (Q1, answered 2026-08-06)
-- ===============================================
-- Vadym chose `letter` (A-F on 90/80/70/60, pass at 70) as the school default,
-- over the design's recommended `pass_fail`. That makes the backfill below a
-- behavioural no-op: `letter` with those bands is exactly what grade_calculator
-- already applies today, so the 12 existing courses keep grading the way they
-- grade now. `pass_fail` stays available as a per-course preset.
--
-- Safety
-- ======
-- Purely additive: new columns on `courses` (every existing row takes the
-- DEFAULT) and one new table. No UPDATE of existing data, no drops. The
-- participation retirement -- the one migration in this phase that rewrites
-- production rows -- is M2 and ships separately, after explicit sign-off.

ALTER TABLE public.courses
    ADD COLUMN grading_scheme TEXT NOT NULL DEFAULT 'letter'
        CHECK (grading_scheme IN ('pass_fail', 'percent', 'five_point', 'letter')),
    ADD COLUMN pass_threshold NUMERIC(5, 2) NOT NULL DEFAULT 70
        CHECK (pass_threshold >= 0 AND pass_threshold <= 100),
    -- «Объём в часах» on the ведомость / transcript. Nullable: only schools
    -- that issue hour-bearing documents fill it in.
    ADD COLUMN academic_hours INTEGER CHECK (academic_hours > 0);

-- Cross-column guard (D8.1): the five-point «3» line cannot sit above 75, or
-- the scheme's own «удовлетворительно» band would be unreachable. Declared as
-- a table constraint so a scheme-only write can never create an invalid pair --
-- the API updates scheme and threshold together through one endpoint, and this
-- is the backstop for anything that bypasses it.
ALTER TABLE public.courses
    ADD CONSTRAINT ck_courses_scheme_threshold
        CHECK (grading_scheme <> 'five_point' OR pass_threshold <= 75);

-- Single-row table holding school-wide settings. `id BOOLEAN PRIMARY KEY
-- DEFAULT true CHECK (id)` is the standard one-row idiom: only `true` is a
-- legal key, so a second row is impossible at the schema level.
--
-- Shaped to survive a future multi-school model: when that day comes the
-- boolean key becomes an org_id and every column travels unchanged.
CREATE TABLE public.org_settings (
    id BOOLEAN PRIMARY KEY DEFAULT TRUE CHECK (id),

    -- Institutional identity, printed on the ведомость header.
    school_name_ru TEXT,
    school_name_en TEXT,
    city TEXT,

    -- Defaults new courses inherit (D1). Deviating from them is an
    -- admin/director action, not a teacher one -- otherwise each teacher picks
    -- independently and a single school's transcript mixes «зачёт», «4» and «B».
    default_grading_scheme TEXT NOT NULL DEFAULT 'letter'
        CHECK (default_grading_scheme IN ('pass_fail', 'percent', 'five_point', 'letter')),
    default_pass_threshold NUMERIC(5, 2) NOT NULL DEFAULT 70
        CHECK (default_pass_threshold >= 0 AND default_pass_threshold <= 100),

    -- Band boundaries per scheme, admin-editable and app-validated (monotonic,
    -- bounded, five_point «3» floor consistent with the threshold). Kept as
    -- JSONB rather than platform constants because RU/UA five-point
    -- conversions genuinely vary -- «5 от 85» is as common in UA practice as
    -- «5 от 90». Without this, onboarding each new school would mean editing
    -- Python constants by hand.
    grade_bands JSONB NOT NULL DEFAULT '{}'::jsonb,

    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_by UUID REFERENCES profiles(id) ON DELETE SET NULL
);

-- Seed the single row with the answered-Q1 defaults so the app never has to
-- cope with "no settings yet". Bands mirror the constants grade_calculator
-- has been applying all along, plus the five-point scale from the design.
INSERT INTO public.org_settings (id, default_grading_scheme, default_pass_threshold, grade_bands)
VALUES (
    TRUE,
    'letter',
    70,
    '{
      "letter": [[90, "A"], [80, "B"], [70, "C"], [60, "D"], [0, "F"]],
      "five_point": [[90, "5"], [75, "4"], [70, "3"], [0, "2"]]
    }'::jsonb
);

-- No direct client access. With the anon key sitting in the browser, GRANTS
-- are the security boundary (the 2026-06-09 lesson, same posture as
-- 20260611200000 and the invitations table): grade bands and the school's
-- pass threshold are institutional configuration, and every read the SPA needs
-- arrives through the FastAPI grading-config endpoint.
REVOKE ALL ON public.org_settings FROM anon, authenticated;

-- Defence in depth, and consistency with the other 33 tables. Grants are the
-- boundary; RLS with zero policies is the backstop if one is ever granted by
-- accident. The backend connects as the table owner and is unaffected.
ALTER TABLE public.org_settings ENABLE ROW LEVEL SECURITY;
