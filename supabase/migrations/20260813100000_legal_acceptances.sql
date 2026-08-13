-- Consent stops living in a browser.
--
-- What was there before
-- =====================
-- The first-run gate showed three bullet points about privacy, a checkbox
-- reading «Я прочитал(а) и принимаю Политику конфиденциальности и Условия
-- использования», and a line saying the full version is always available from
-- the footer.
--
-- There was no full version. There was no terms-of-use document at all. There
-- was no link in the footer. And the acceptance was written to
-- `localStorage` under `equip.privacy.accepted.<userId>` — so clearing a
-- browser erased every trace that anybody had ever agreed to anything, and a
-- second device never had one to begin with.
--
-- Proving that a person agreed, and to what, is the entire job of a consent
-- record. The platform was doing none of it, on a platform that admits
-- sixteen-year-olds.
--
-- Why the version and the hash, and not a foreign key
-- ==================================================
-- Same principle as the ведомость letterhead (20260810230000), the certificate
-- letterhead (20260813020000) and the submission declaration (20260812160000):
-- what somebody agreed to has to survive the thing they agreed to being
-- changed. A row pointing at a `legal_documents` table would say "they
-- accepted the privacy policy" while the privacy policy quietly became
-- something else underneath it.
--
-- So each row carries the version string and the SHA-256 of the body as it was
-- served. The documents themselves are files in the repository
-- (`backend/app/legal/documents/`), which means the server can still produce
-- the exact text any historical hash refers to, and a change of a single word
-- is visible in the record afterwards.
--
-- `locale` is stored because a student who read the Russian text agreed to the
-- Russian text. Both translations share a version, so "has this person
-- accepted the current policy" still has one answer.
--
-- `ip` exists for the same reason it exists on a submission declaration: it is
-- evidence the acceptance happened. It is named in the privacy policy itself,
-- and used for nothing else.

CREATE TABLE public.legal_acceptances (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    document_slug text NOT NULL,
    version text NOT NULL,
    locale text NOT NULL,
    content_sha256 text NOT NULL,
    accepted_at timestamptz NOT NULL DEFAULT now(),
    ip text,
    -- One row per person per version. A double-click is not new consent, and
    -- two rows for one version would leave two answers to "when did they
    -- agree" with no way to tell which is the real one.
    CONSTRAINT uq_legal_acceptances_user_doc_version UNIQUE (user_id, document_slug, version)
);

CREATE INDEX ix_legal_acceptances_user ON public.legal_acceptances (user_id);

COMMENT ON TABLE public.legal_acceptances IS
    'Who accepted which version of which policy, with the hash of the text they were shown.';
COMMENT ON COLUMN public.legal_acceptances.content_sha256 IS
    'SHA-256 of the document body as served, so "you agreed to this" stays a checkable claim.';
COMMENT ON COLUMN public.legal_acceptances.locale IS
    'The translation actually read. Both share a version; the text they saw is the one recorded.';
COMMENT ON COLUMN public.legal_acceptances.ip IS
    'Evidence the acceptance happened. Disclosed in the privacy policy; used for nothing else.';
