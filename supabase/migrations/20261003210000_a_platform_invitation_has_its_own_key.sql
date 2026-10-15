-- A platform invitation has its own key.
--
-- `ix_invitations_one_pending_per_scope` (20260912140000) keeps one pending
-- invitation per (organization, email, role, course). It was written when
-- a platform invitation covered everything a school could offer, so the
-- two could never both be needed. Since 2026-10-03 a platform invitation
-- grants an account and nothing else (invitation_service), and it is filed
-- under an organization only because the column is NOT NULL — so the
-- admin's "come to Equip" and a director's "join our school" to the same
-- address shared a key, and whichever came second was refused.
--
-- The scope joins the key. The index only gets looser: every set of rows
-- the old one allowed, this one allows, so it cannot fail on existing data.
-- Two pending invitations of the same kind still collide — that is the
-- deduplication the index is for.
--
-- Safe before the backend that needs it: the previous release never writes
-- a platform row beside a school row (it revoked one for the other).

DROP INDEX IF EXISTS public.ix_invitations_one_pending_per_scope;

CREATE UNIQUE INDEX ix_invitations_one_pending_per_scope
  ON public.invitations (organization_id, email, role, scope, coalesce(course_id, ''))
  WHERE status = 'pending';
