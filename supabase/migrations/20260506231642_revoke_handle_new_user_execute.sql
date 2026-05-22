-- Supabase migration: revoke_handle_new_user_execute
-- Version: 20260506231600
--
-- Hardens the auto-profile-creation trigger function. Postgres functions
-- inherit EXECUTE for PUBLIC by default, and Supabase auto-exposes any
-- SECURITY DEFINER function in the public schema via PostgREST as
-- /rest/v1/rpc/<name>. Revoking EXECUTE removes that RPC endpoint so
-- handle_new_user can only fire as the AFTER INSERT trigger on
-- auth.users (trigger invocation does not check EXECUTE on the function).
--
-- Addresses Supabase Advisor lints 0028 and 0029
-- (anon_/authenticated_security_definer_function_executable).

REVOKE EXECUTE ON FUNCTION public.handle_new_user() FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION public.handle_new_user() FROM anon;
REVOKE EXECUTE ON FUNCTION public.handle_new_user() FROM authenticated;
