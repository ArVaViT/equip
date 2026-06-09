-- SECURITY: revoke direct client SELECT on the answer-key tables.
--
-- The browser talks to Postgres directly with the publishable/anon key + the
-- user's JWT (supabase-js). The SELECT policies on these tables exposed ALL
-- columns — including ``is_correct`` — to any authenticated user, so a student
-- could read the answer key from the console (`supabase.from('quiz_options')
-- .select('*')`) BEFORE submitting, bypassing the backend's answer-stripping.
--
-- The app never reads these tables via the client (all quiz / daily-challenge
-- data is served through the FastAPI backend, which connects as a privileged
-- role and is unaffected). Revoking client SELECT closes the leak with no
-- functional impact; the RLS SELECT policies become inert without the grant.
REVOKE SELECT ON public.quiz_options FROM anon, authenticated;
REVOKE SELECT ON public.daily_challenge_options FROM anon, authenticated;
