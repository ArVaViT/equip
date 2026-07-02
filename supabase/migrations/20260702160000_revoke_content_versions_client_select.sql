-- SECURITY: revoke direct client SELECT on content_versions.
--
-- After the Phase-5 migrations dropped the text columns off the entity
-- tables, ``content_versions`` became the sole store of ALL course /
-- announcement / quiz text. Its ``content_versions_anon_read`` policy let an
-- UNAUTHENTICATED caller scrape the full text of every course — including
-- unpublished drafts and cohort-gated content — with just the publishable
-- anon key (`supabase.from('content_versions').select('*')`). The
-- authenticated policy was equally broad.
--
-- The app never reads this table via the client (all content is served
-- through the FastAPI backend, which connects as a privileged role and is
-- unaffected). Mirrors 20260608200000_revoke_client_answer_key_reads.
DROP POLICY IF EXISTS content_versions_anon_read ON public.content_versions;
DROP POLICY IF EXISTS content_versions_authenticated_read ON public.content_versions;
REVOKE SELECT ON public.content_versions FROM anon, authenticated;
