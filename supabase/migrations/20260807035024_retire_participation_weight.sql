-- Grading redesign, Phase 1 / M2: retire "participation" as a weighted grade
-- category. Design: grading-system-redesign.md (Accepted 2026-08-06), D5.
--
-- Why it goes
-- ===========
-- "Participation" was a third weighted bucket fed by chapter-completion
-- percentage. It is double bookkeeping: completion already lives in
-- `enrollments.progress` and already gates the certificate, and every passed
-- quiz counts twice — once in the quiz average, once again through the
-- chapter it completes.
--
-- None of the eight Bible-college handbooks surveyed for the redesign treats
-- attendance or participation as a positive weighted component; the native
-- concepts are attendance-as-gate and зачёт for practical work. Completion IS
-- the attendance gate, so the category buys nothing and costs predictability:
-- a teacher cannot reconstruct a grade on paper when a fifth of it comes from
-- a percentage nobody entered.
--
-- What this does to real data
-- ===========================
-- Two cases, and the distinction matters more than it looks.
--
-- **A course still on the untouched platform default 30/50/20 becomes 40/60**,
-- the new default — not the 38/62 that proportional arithmetic would produce.
-- Nobody ever chose 30/50/20; it is what the old schema handed out. Carrying
-- that non-decision forward through a rounding step would leave the school
-- with two different splits — legacy courses at 38/62, new ones at 40/60 —
-- and hand teachers a number no one can reproduce on paper. All 12 production
-- courses are in this case.
--
-- **A course whose teacher actually set the weights keeps its ratio**, with
-- participation's share folded proportionally:
--
--   quiz 60, assignment 20  ->  60/(60+20) = 75 -> 75/25
--
-- Rounding lands on the quiz side and assignment takes the remainder, so
-- `quiz + assignment + participation = 100` holds for every row in one pass.
-- Ties (a .5 share) round away from zero here; the API normalizer resolves
-- them the same way, so a stale browser tab and this migration agree.
--
-- The pure-participation edge (both other weights zero — unreachable through
-- the UI, reachable by a direct write) falls back to the 40/60 default: there
-- is no ratio to preserve, so inventing one would be arbitrary.
--
-- **This is the only migration in Phase 1 that rewrites existing rows.**
-- Run with Vadym's explicit go-ahead on 2026-08-07. It is safe at this moment
-- for a reason that will not hold later: `student_grades` has 0 rows and no
-- student has ever been shown a computed grade, so no visible number changes
-- for anyone.
--
-- The column itself is kept (schema compatibility, and the calculator still
-- reads it during the transition); the API pins it to 0 and the UI hides it.

UPDATE public.courses
SET
    quiz_weight = CASE
        -- Untouched platform default -> the new platform default.
        WHEN quiz_weight = 30 AND assignment_weight = 50 AND participation_weight = 20 THEN 40
        -- No ratio to preserve.
        WHEN quiz_weight + assignment_weight = 0 THEN 40
        -- Deliberate weights -> keep the ratio.
        ELSE round(quiz_weight * 100.0 / (quiz_weight + assignment_weight))
    END,
    assignment_weight = 100 - (
        CASE
            WHEN quiz_weight = 30 AND assignment_weight = 50 AND participation_weight = 20 THEN 40
            WHEN quiz_weight + assignment_weight = 0 THEN 40
            ELSE round(quiz_weight * 100.0 / (quiz_weight + assignment_weight))
        END
    ),
    participation_weight = 0
WHERE participation_weight > 0;

-- Defaults follow the data. Without this, every course created after the
-- migration would resurrect participation at 20 and quietly reintroduce the
-- double counting this migration exists to remove.
ALTER TABLE public.courses
    ALTER COLUMN quiz_weight SET DEFAULT 40,
    ALTER COLUMN assignment_weight SET DEFAULT 60,
    ALTER COLUMN participation_weight SET DEFAULT 0;

-- Belt and braces: nothing may set a positive participation weight again.
-- The API normalizes stale clients rather than rejecting them, but a direct
-- database write (service script, MCP call) has no such courtesy — and the
-- whole point of D5 is that the retirement is atomic, not cosmetic.
ALTER TABLE public.courses
    ADD CONSTRAINT ck_courses_participation_retired
        CHECK (participation_weight = 0);
