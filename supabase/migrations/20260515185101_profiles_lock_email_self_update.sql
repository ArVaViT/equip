-- Supabase migration: profiles_lock_email_self_update
-- Version: 20260515184958
--
-- MEDIUM severity: profile-row spoofing for social engineering.
--
-- The existing ``profiles_update_own_no_role`` policy correctly prevents
-- role escalation but its WITH CHECK only protects ``role``. A user
-- could PATCH ``profiles.email`` (or ``created_at``) via PostgREST to
-- any value:
--
--   await supabase.from('profiles')
--     .update({ email: 'admin@equipbible.com' })
--     .eq('id', myId);
--
-- ``profiles.email`` is a synced copy of ``auth.users.email`` (the
-- canonical column for auth). The JWT ``sub`` claim is still the
-- user's real UUID, so this isn't a session-takeover -- but
-- ``profiles.email`` IS the column the backend reads when surfacing
-- the user's identity in:
--   * analytics.py L65-66       (course-level student roster)
--   * grades.py L112            (StudentCalculatedGrade.student_email)
--   * student_progress_service  (teacher's "see all students" view)
--
-- A student spoofing their email to ``admin@equipbible.com`` then
-- showing up in a teacher's grade roster is a clean social-engineering
-- vector ("I'm the admin, please regrade this"). And teachers tend to
-- trust the email column more than the UUID.
--
-- Fix: replace the existing UPDATE policy with one whose WITH CHECK
-- also pins ``email``, ``id``, and ``created_at`` to their current
-- values. Only ``full_name``, ``avatar_url``, ``preferred_locale``,
-- ``updated_at`` remain client-mutable (matching the
-- ``usersService.updateProfile`` frontend contract). ``role`` stays
-- pinned via the existing subquery -- carried verbatim.
--
-- There is currently no SPA flow that changes a user's email
-- (``services/auth.ts`` only calls ``supabase.auth.updateUser`` with
-- ``{ password }``), and no trigger that mirrors ``auth.users.email``
-- changes back into ``profiles.email`` -- so locking the column is
-- not a UX regression. If we add an email-change flow later, the
-- right shape is a server-mediated POST (which runs as ``postgres``
-- and bypasses RLS) or a new auth-users-on-update trigger.

DROP POLICY IF EXISTS profiles_update_own_no_role ON public.profiles;

CREATE POLICY profiles_update_own_safe_fields ON public.profiles
  FOR UPDATE
  TO authenticated
  USING (
    (SELECT auth.uid()) = id
  )
  WITH CHECK (
    (SELECT auth.uid()) = id
    -- role: must match the current row (no escalation)
    AND role = (
      SELECT p.role FROM public.profiles p WHERE p.id = (SELECT auth.uid())
    )
    -- email: must match the current row (no spoofing)
    AND email = (
      SELECT p.email FROM public.profiles p WHERE p.id = (SELECT auth.uid())
    )
    -- created_at: immutable
    AND created_at IS NOT DISTINCT FROM (
      SELECT p.created_at FROM public.profiles p WHERE p.id = (SELECT auth.uid())
    )
  );

COMMENT ON POLICY profiles_update_own_safe_fields ON public.profiles IS
  'Self-update is allowed only on full_name / avatar_url / preferred_locale / updated_at. role / email / id / created_at are pinned to current values so PostgREST clients cannot spoof identity columns. Trigger-sync from auth.users runs as postgres and bypasses this policy.';
