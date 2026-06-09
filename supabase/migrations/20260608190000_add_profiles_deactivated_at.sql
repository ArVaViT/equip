-- Soft-delete support for user accounts.
--
-- The admin "delete user" action now DEACTIVATES rather than purges: it sets
-- profiles.deactivated_at and the backend blocks that account's login, but all
-- owned data (courses, grades, certificates) is preserved so the account can
-- be restored. This replaces the old behaviour where data was hard-deleted but
-- the auth.users identity lingered and resurrected an empty profile on re-login.
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS deactivated_at timestamptz;
