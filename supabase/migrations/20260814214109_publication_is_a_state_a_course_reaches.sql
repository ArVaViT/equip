-- Publication is a state a course reaches, not a button that fires.
--
-- What publishing meant until now
-- ==============================
-- `status` flipped to 'published' the moment the teacher asked for it, and the
-- translation of the course started afterwards — in a try/except that swallowed
-- its own failures, because a teacher must never lose a save. The course was in
-- the catalog while some of its languages were still empty. A student who had
-- chosen Ukrainian could open a course whose Ukrainian did not exist yet, and
-- nothing in the system considered that a problem: the only readiness gate,
-- `compute_readiness`, says "never hard-blocks" in its own docstring and has no
-- check about translation at all.
--
-- For a platform whose promise is that a German writes a course and Ukrainians
-- and Americans take it, a course that is whole in one language and partial in
-- another is not a smaller version of the course. It is a different course, and
-- the second group is quietly given the lesser one.
--
-- The middle state
-- ================
-- 'publishing' is a course the teacher has sent out that is not yet whole:
-- some locale is missing a field, or a translation came back and failed its
-- structural check (`content_versions.status = 'needs_review'`, added in
-- 20260814172522). It is treated as unpublished by every reader — the code
-- compares against 'published' everywhere, so the catalog, enrollment, and
-- access checks needed no changes at all. The worker promotes it to
-- 'published' as soon as every language has it.
--
-- What this deliberately does NOT do
-- ==================================
-- An already-published course does not fall back to 'publishing' when its
-- teacher edits a word. Read the rule literally and a typo fix in one sentence
-- would pull a live course out from under every student in every language
-- until the machine caught up. Students keep reading the version that was
-- checked; the new text replaces it per field, as each field's translation
-- passes. Publication is not un-done by an edit.
--
-- Existing rows are untouched: 'draft' and 'published' keep their meaning, and
-- no course is retroactively moved into the new state.

ALTER TABLE public.courses
    DROP CONSTRAINT IF EXISTS chk_courses_status;

ALTER TABLE public.courses
    ADD CONSTRAINT chk_courses_status
    CHECK (status IN ('draft', 'publishing', 'published'));

COMMENT ON COLUMN public.courses.status IS
    'draft = owner and admins only. publishing = the teacher asked for it and some language does not have it yet; invisible to students, promoted by the translation worker when complete. published = in the catalog.';
