-- An invitation keeps only the hash of its token — step 2 of 2 (contract).
--
-- APPLY ONLY ONCE THE BACKEND FROM PR #1389 IS LIVE IN PRODUCTION. The
-- previous backend reads and writes `token`; after this it would answer 500
-- on every invitation route.
--
-- Step 1 (20261015213140) added `token_hash`, backfilled it and kept it
-- filled from `token` by a trigger while both backends could be running.
-- With only the new backend left, nothing writes `token` any more, so:
-- the trigger goes, the plain tokens go — the whole point of the rollout —
-- and `token_hash` becomes NOT NULL.
--
-- Refuses rather than guesses if any row has no hash: that would be an
-- invitation nobody can open, and the reason should be looked at first.

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM public.invitations WHERE token_hash IS NULL) THEN
    RAISE EXCEPTION 'an invitation has no token_hash; step 1 did not cover it';
  END IF;
END $$;

DROP TRIGGER IF EXISTS trg_invitations_token_hash_from_token ON public.invitations;
DROP FUNCTION IF EXISTS public.invitation_token_hash_from_token();

ALTER TABLE public.invitations ALTER COLUMN token_hash SET NOT NULL;

-- Its UNIQUE constraint (invitations_token_key) goes with it.
ALTER TABLE public.invitations DROP COLUMN IF EXISTS token;
