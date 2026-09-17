-- A small edit is told, not signed.
--
-- What this is for
-- ================
-- `legal_acceptances` answers "did this person agree, and to what". It is the
-- wrong table for the other half of the promise the documents now make: that a
-- correction, a clarification or a shortened retention window reaches people as
-- a *notice* rather than as a blocking consent screen. Writing a row into
-- `legal_acceptances` when somebody dismisses a notice would assert agreement
-- to something nobody was asked to agree to, which is exactly the confusion the
-- provider list was kept off that table to avoid.
--
-- So: a second, smaller table. A row here means "this person was told about
-- version X of document Y and closed the banner". It is not consent, it is not
-- evidence of consent, and nothing in the product treats it as either.
--
-- Why this exists at all, rather than a browser flag
-- ==================================================
-- A `localStorage` flag would re-show the banner on every other device the
-- person uses, which trains people to dismiss banners without reading them —
-- the same failure mode the version-bump-for-everything approach had, one
-- notch quieter. The registry in `backend/app/legal/registry.py` decides which
-- versions are notice-only (`Revision.consent = False`); this table records who
-- has seen each one.
--
-- What is deliberately not here
-- =============================
-- No IP address and no User-Agent. `legal_acceptances.ip` and
-- `submission_declarations.ip` exist because the privacy policy names those two
-- moments and because an acceptance and a declaration are things somebody may
-- one day have to prove. Dismissing a banner is neither, and 20260917031817
-- removed exactly this kind of incidental address collection from `audit_logs`.

CREATE TABLE public.legal_notices_seen (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    document_slug text NOT NULL,
    version text NOT NULL,
    seen_at timestamptz NOT NULL DEFAULT now(),
    -- One row per person per version, for the same reason as on
    -- `legal_acceptances`: a double-click is not a second dismissal, and two
    -- rows would leave two answers to "when were they told".
    CONSTRAINT uq_legal_notices_seen_user_doc_version UNIQUE (user_id, document_slug, version)
);

CREATE INDEX ix_legal_notices_seen_user ON public.legal_notices_seen (user_id);

-- Same posture as `legal_acceptances` in 20260908170000: RLS on, no policies.
-- The backend reaches Postgres as the owning role, which carries BYPASSRLS;
-- nothing in the client ever reads or writes this table through PostgREST, so a
-- policy written now would be a policy invented ahead of its caller — the kind
-- that gets written `USING (true)`.
ALTER TABLE public.legal_notices_seen ENABLE ROW LEVEL SECURITY;

COMMENT ON TABLE public.legal_notices_seen IS
    'Who has been told about a notice-only version of a document. Not consent.';
COMMENT ON COLUMN public.legal_notices_seen.version IS
    'The version they were told about, which is the current one at the moment they were told.';
