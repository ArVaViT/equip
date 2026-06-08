-- Narrow the profiles.role CHECK to the three roles the app actually uses.
--
-- 'pending_teacher' was removed functionally by
-- 20260531120000_remove_pending_teacher_role_handle_new_user.sql (every row
-- downgraded to 'student', the signup trigger rewritten), but the CHECK
-- constraint was never narrowed — so prod still permitted a value that
-- neither UserRole (backend/app/models/user.py) nor the frontend UserRole
-- accepts. This makes the DB exactly match code.
--
-- Verified before applying: 0 rows with role='pending_teacher', 0 RLS
-- policies reference the value.
ALTER TABLE public.profiles DROP CONSTRAINT IF EXISTS chk_profiles_role;
ALTER TABLE public.profiles
    ADD CONSTRAINT chk_profiles_role
    CHECK (role = ANY (ARRAY['admin'::text, 'teacher'::text, 'student'::text]));
