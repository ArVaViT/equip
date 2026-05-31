-- Floor for iCal token ``iat`` claims per user.
--
-- The original iCal token rotation design relied on the JWT ``iat``
-- claim being validated at decode time. PyJWT does NOT validate
-- ``iat`` by default, so a leaked subscribe URL stayed valid for
-- the full 365-day TTL even after the user clicked "rotate".
--
-- This column gives the feed verifier a server-side floor: when a
-- user calls ``POST /calendar/ical/token`` we stamp this to the new
-- token's ``iat``. The feed route rejects any token whose ``iat``
-- is older than the stored floor — that's what makes rotation
-- actually invalidate the old token.
--
-- Nullable. NULL means "no rotation yet"; the verifier treats a
-- valid signature + scope + audience + non-expired token as
-- acceptable. The first ``/token`` call stamps it; every subsequent
-- call advances it.

ALTER TABLE public.profiles
    ADD COLUMN IF NOT EXISTS calendar_ical_min_iat BIGINT;
