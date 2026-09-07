-- Onboarding is finished once.
--
-- The complaint
-- =============
-- «Когда пользователь уже существует и логинится заново, зачем снова
-- принимать конфиденциальность, настраивать акк и проходить онбординг?»
--
-- Consent was already fixed (20260813, `legal_acceptances`): the server
-- knows who accepted what, and the browser flag is a cache of that answer.
-- The other two screens — account setup and the first-course picker — were
-- never fixed the same way. Their "done" marks lived only in `localStorage`
-- under the user's id, so a second device, a private window, or cleared site
-- data had never seen them, and the flow ran again from the top.
--
-- The change
-- ==========
-- One nullable timestamp on `profiles`. NULL means the flow has not been
-- finished on any device; a value means it has, and the client shows nothing.
-- The backend writes it once, through `POST /users/me/onboarding/complete`,
-- and never moves it. It is deliberately NOT in `legal_acceptances` and NOT a
-- row per step: this is a preference about a wizard, not evidence of consent,
-- and the wizard has been cut to the one step that matters (the picker) so
-- there is nothing finer-grained to remember.
--
-- Backfill
-- ========
-- Everybody who has ever enrolled in a course has been past the picker, or
-- found the catalogue on their own — either way they should not meet the
-- welcome flow again. Their mark is the moment of their first enrollment,
-- which is the truest date we have. Accounts with no enrollment are left
-- NULL: the client heals them itself on the next visit from a browser that
-- holds the old flag (it reports the completion to the server), and a
-- brand-new device shows the picker once, which for somebody with no
-- courses is the right screen anyway.
--
-- Not applied by `supabase db push` — the migration markers in this
-- directory and in production have diverged. Run this file by hand in the
-- SQL editor and then insert its version into
-- `supabase_migrations.schema_migrations`.

ALTER TABLE public.profiles
    ADD COLUMN IF NOT EXISTS onboarding_completed_at timestamp with time zone;

COMMENT ON COLUMN public.profiles.onboarding_completed_at IS
    'When this person finished the first-run flow on any device. NULL = show it. Written once by the API and never moved; not a consent record (see legal_acceptances).';

UPDATE public.profiles AS p
SET onboarding_completed_at = COALESCE(e.first_enrolled_at, now())
FROM (
    SELECT user_id, MIN(enrolled_at) AS first_enrolled_at
    FROM public.enrollments
    GROUP BY user_id
) AS e
WHERE e.user_id = p.id
  AND p.onboarding_completed_at IS NULL;
