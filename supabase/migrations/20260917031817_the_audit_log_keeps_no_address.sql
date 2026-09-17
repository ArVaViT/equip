-- The audit log keeps no address.
--
-- The Privacy Policy says an IP address is stored at two moments only:
-- accepting a legal document (legal_acceptances.ip) and handing in work
-- (submission_declarations.ip). audit_logs nevertheless carried ip_address
-- and user_agent, and the backend filled them on nearly every audited action
-- (638 of 652 rows on 2026-09-16) -- enrolling, changing a setting, creating
-- a course. The backend stopped writing them in the same change; this removes
-- the columns so nothing can start writing them again without a migration
-- somebody has to read.
--
-- NULL first, then DROP. DROP COLUMN on its own only hides the column in the
-- catalog: the bytes stay in every existing tuple until the row is next
-- rewritten. The UPDATE writes new tuple versions without the values, and
-- autovacuum reclaims the old ones. (Point-in-time backups still hold the
-- old values until they age out of the project's backup window.)
--
-- Apply AFTER the backend that no longer maps these columns is deployed: the
-- previous backend selects and inserts them, so dropping first would turn
-- the admin audit page into a 500 and lose audit rows until the deploy.

UPDATE public.audit_logs
   SET ip_address = NULL,
       user_agent = NULL
 WHERE ip_address IS NOT NULL
    OR user_agent IS NOT NULL;

ALTER TABLE public.audit_logs
  DROP COLUMN IF EXISTS ip_address,
  DROP COLUMN IF EXISTS user_agent;
