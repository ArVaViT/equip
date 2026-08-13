-- The certificate becomes a document, and keeps its own words.
-- Design: equip-design/decisions/004-art-direction.md; the same principle the
-- ведомость already runs on (20260810210000_sheets_keep_their_own_names).
--
-- Why a certificate needs a letterhead of its own
-- ==============================================
-- Until now the platform issued a row: a number, a date, a status. What a
-- student actually receives from a school is a document with the school's name
-- on it, their own name spelled the way the institution spells it, and two
-- signature lines. That document is the only part of this product a stranger
-- ever sees — an employer, a pastor, a bishop — and it is the artefact
-- everything else exists to produce.
--
-- Rendering it from live data would repeat a bug already fixed once. A school
-- that renames itself in March must not rewrite what it certified in February;
-- a student who marries and changes her surname must not have last year's
-- certificate silently re-issued in a name she did not hold when she earned it.
-- The grade was frozen onto this row by M6 for exactly that reason. The words
-- were not, and they are the part a person reads.
--
-- Captured at issuance, never after
-- =================================
-- These columns are written once, in `admin_approve`, at the moment the
-- certificate becomes one. Existing rows stay NULL: the four certificates
-- issued before this migration were issued without a letterhead, and inventing
-- one for them retroactively would be putting a school's name on a document it
-- did not sign. They render with what they have.

ALTER TABLE public.certificates
    ADD COLUMN school_name text,
    ADD COLUMN school_city text,
    ADD COLUMN student_name text,
    ADD COLUMN teacher_name text;

COMMENT ON COLUMN public.certificates.school_name IS
    'The issuing school as it was named at issuance. Never re-read: a school that renames itself must not rewrite what it already certified.';
COMMENT ON COLUMN public.certificates.student_name IS
    'The name the certificate was issued in. A later change of surname does not rewrite the document.';
COMMENT ON COLUMN public.certificates.teacher_name IS
    'Who taught it, for the signature line — the name at issuance, not the current one.';
