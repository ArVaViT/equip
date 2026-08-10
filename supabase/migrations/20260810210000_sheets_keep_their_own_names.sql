-- Correction to M5 (20260810180000), found before the printable was built.
--
-- A signed page must keep its own words
-- =====================================
-- The sheet froze the numbers and left the words live, which is half a
-- snapshot and therefore not one:
--
--   * `student_name` was read from `profiles` at every request. A student who
--     marries and changes her surname rewrites a document signed under the old
--     one — silently, retroactively, on paper somebody has already filed.
--   * `cohort_name` was resolved through the admin helper, which picks
--     "whichever locale was created first" as a deterministic representative.
--     For a school whose English name happened to be entered first, the
--     Russian ведомость got the English поток name.
--   * The course title was not captured at all, so the printable had to fetch
--     it live — and course titles are edited.
--
-- Same rule as the numbers: what the document said when it was signed is what
-- it says.
--
-- Why the sheet records its language
-- ==================================
-- The interface locale belongs to the reader and changes per session. A signed
-- document's language belongs to the document: printed in English, signed, and
-- filed, that paper is English forever.
--
-- Today every sheet closes in English, by decision. The column exists so that
-- adding a language later costs nothing — without it, the day a second
-- language appears, every sheet already in the cabinet is of unknown language
-- and there is nothing to read it back from.

ALTER TABLE public.grade_sheets
    ADD COLUMN locale TEXT NOT NULL DEFAULT 'en',
    -- The course title as it read at closing, in the sheet's language.
    ADD COLUMN course_title TEXT;

ALTER TABLE public.grade_sheet_rows
    -- The name the document was signed under.
    ADD COLUMN student_name TEXT;
