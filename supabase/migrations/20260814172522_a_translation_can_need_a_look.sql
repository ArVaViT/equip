-- A translation can be finished and still not be right.
--
-- What `ok` meant until now
-- ========================
-- `content_versions.status = 'ok'` was written whenever the Gemini call
-- returned without raising. The provider checks the envelope — are there
-- candidates, are there parts, did finishReason say STOP, is the text non-empty
-- — and nothing in the pipeline ever looked at the content. A response that
-- dropped a scripture marker, halved the markup of a lesson, answered in the
-- wrong language, or appended a paragraph explaining itself is a well-formed
-- envelope. Every reader in the platform treats its `ok` as "this translation
-- is good", because `ok` was the only thing a finished translation could be.
--
-- That is what makes the rule unenforceable. "Do not publish until every
-- language is translated AND checked" needs a state that can say *checked*, and
-- a status that means "no exception was raised" cannot say it.
--
-- The third state
-- ===============
-- `needs_review` is a translation that came back and failed a structural check
-- against its source: markers, markup, placeholders, numbers, language, length.
-- The text is kept — whoever reviews it has to see what the model actually
-- said — but the row is not servable. Readers filter on `status = 'ok'`, so a
-- `needs_review` row reads as "not translated yet" rather than being quietly
-- shown to a student. `review_reason` carries the machine's account of what is
-- wrong, in a sentence a person can act on.
--
-- What this does not claim
-- ========================
-- Not a judgement of quality. Nothing running locally can make one, and the
-- research is consistent that quality in the general case is not measurable
-- without a reader of the language. These checks catch the failures that are
-- structural — and those are the ones that corrupt a lesson silently, where a
-- clumsy sentence merely reads badly.
--
-- Existing rows are untouched: they were written under the old meaning of `ok`
-- and re-labelling them retroactively would be inventing a check that never
-- ran. They are re-validated the next time their source changes.

ALTER TABLE public.content_versions
    DROP CONSTRAINT IF EXISTS content_versions_status_check;

ALTER TABLE public.content_versions
    ADD CONSTRAINT content_versions_status_check
    CHECK (status IN ('ok', 'needs_review', 'failed', 'failed_permanent'));

ALTER TABLE public.content_versions
    ADD COLUMN IF NOT EXISTS review_reason text;

COMMENT ON COLUMN public.content_versions.review_reason IS
    'Why a needs_review row is not servable, in words a person can act on. NULL on every other status.';

COMMENT ON COLUMN public.content_versions.status IS
    'ok = passed the structural check and is servable. needs_review = the provider answered and the answer failed that check; text kept, not served. failed / failed_permanent = the provider call itself did not produce text.';

-- Finding the queue: every row waiting on a human, newest first.
CREATE INDEX IF NOT EXISTS ix_content_versions_needs_review
    ON public.content_versions (locale, created_at DESC)
    WHERE superseded_by IS NULL AND status = 'needs_review';
