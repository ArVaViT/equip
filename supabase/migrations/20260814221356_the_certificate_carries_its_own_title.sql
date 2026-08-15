-- The certificate carries its own title, in English, frozen at issuance.
--
-- What it did instead
-- ===================
-- Every other word on the document was frozen when the certificate was issued
-- — the school's name, the city, the student's name, the teacher's
-- (20260813020000). The course title was not. It was resolved live from
-- `content_versions` at the language of whoever happened to be looking:
-- `display_locale = normalize_locale(accept_language)` on the verify endpoint,
-- with `Vary: Accept-Language` on the response.
--
-- So an employer in Berlin and an employer in Kyiv verifying the same
-- credential were shown different course names, and both would change again
-- the day someone re-ran the translation. The single field a stranger actually
-- reads was the one field that could still move.
--
-- Why English rather than the recipient's language
-- ================================================
-- A certificate is the one artefact of this platform that leaves it. It is
-- read by people who have no account here — an employer, a pastor, a bishop —
-- and it may be read years later by someone the student has never met. It has
-- to say one thing, and the same thing, to all of them. The grade sheet
-- already works this way (`SHEET_LOCALE = "en"`); the certificate now matches.
--
-- Old certificates
-- ================
-- Rows issued before this migration have NULL here. They keep resolving the
-- way they did — through `archived_course_title` or the live course — because
-- back-filling would be inventing a snapshot that was never taken. New
-- issuances write it; that is the whole change.

ALTER TABLE public.certificates
    ADD COLUMN IF NOT EXISTS course_title text;

COMMENT ON COLUMN public.certificates.course_title IS
    'The course name as printed on the document: English, captured at issuance, never re-read. A stranger verifying this credential must be shown the same words as everyone else.';
