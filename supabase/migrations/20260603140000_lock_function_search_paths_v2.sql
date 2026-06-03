-- Supabase migration: lock_function_search_paths_v2
-- Version: 20260603140000
--
-- Follow-up to 20260422215624. Two functions added after that
-- migration carry mutable search_path (Supabase security advisor
-- 0011_function_search_path_mutable). Lock them to the same
-- ``pg_catalog, public`` scope the earlier batch used.
--
-- Why this matters: a mutable search_path on a SECURITY-sensitive
-- function (or any function called from a trigger that touches
-- privileged tables) is a privilege-escalation hazard. Even though
-- these two are SECURITY INVOKER, future maintenance could flip
-- them — locking the search_path now is cheap insurance.

ALTER FUNCTION public.content_versions_set_updated_at() SET search_path = pg_catalog, public;
ALTER FUNCTION public.dc_schedule_assert_publishable() SET search_path = pg_catalog, public;
