-- SECURITY (defense-in-depth): revoke client write grants on backend-managed
-- tables. These are safe TODAY only because no permissive write policy exists
-- (RLS deny-by-default), but the grants themselves are wrong and one stray
-- `CREATE POLICY ... USING (true)` away from catastrophe:
--   * audit_logs must be tamper-proof (an audit table granting INSERT/UPDATE/
--     DELETE to anon/authenticated defeats its purpose);
--   * a student must never be able to self-grant quiz_extra_attempts;
--   * a student must never UPDATE/DELETE a submitted quiz_answer.
-- All writes to these tables go through the FastAPI backend (service role),
-- which is unaffected. quiz_answers keeps INSERT (its insert policy is the
-- legitimate submit path); only the post-submit mutation verbs are revoked.
REVOKE INSERT, UPDATE, DELETE ON public.audit_logs FROM anon, authenticated;
REVOKE INSERT, UPDATE, DELETE ON public.quiz_extra_attempts FROM anon, authenticated;
REVOKE UPDATE, DELETE ON public.quiz_answers FROM anon, authenticated;
