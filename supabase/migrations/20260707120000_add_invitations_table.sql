-- One-time, unique-token email invites for the teacher/student roles.
--
-- Context
-- =======
-- Self-signup always lands as 'student' (20260531120000 rewrote
-- handle_new_user so a claimed role in signup metadata is ignored, and
-- 20260515183845 blocks role escalation at signup). There is no
-- self-service path to a teacher account. This table backs an
-- admin-issued, single-use invite link that promotes the invited email
-- to 'teacher' or 'student' once redeemed. Admin escalation is
-- deliberately NOT invitable here -- an admin role can only be granted
-- via the existing manual PUT /users/admin/users/{id}/role route.
--
-- Redemption model
-- ================
-- The backend never calls the Supabase Auth admin API to mint the user.
-- The invited person signs up or logs in normally (landing as 'student'
-- via the existing trigger), then calls the authenticated
-- POST /invitations/accept with the token. The backend checks the
-- token against THIS table (connects as postgres, bypassing grants
-- below entirely) and, once it confirms the caller's email matches the
-- invite, flips profiles.role. The token itself -- not RLS -- is the
-- capability; no direct client access to this table is ever needed, so
-- every grant is revoked below (mirrors the "GRANTS are the boundary"
-- posture from 20260611200000).
--
-- Single-use race safety: the accept path UPDATEs WHERE status='pending'
-- and checks the affected row count, so two concurrent accepts (double
-- click, retried request) can't both succeed. The partial unique index
-- below additionally stops two 'pending' rows for the same
-- (email, role) pair from ever coexisting, so a rapid double "Invite"
-- click in the admin UI can't fan out duplicate rows either.

CREATE TABLE invitations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('teacher', 'student')),
    token TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'accepted', 'revoked')),
    invited_by UUID REFERENCES profiles(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    accepted_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ NOT NULL DEFAULT (NOW() + INTERVAL '7 days')
);

-- Admin list view: "invitations for this email/role, most recent first".
CREATE INDEX ix_invitations_email_role ON invitations (email, role, created_at DESC);

-- Resend/dedupe guard at the DB level, not just app logic.
CREATE UNIQUE INDEX ix_invitations_one_pending_per_email_role
    ON invitations (email, role) WHERE status = 'pending';

-- No direct client access -- every read/write goes through the FastAPI
-- backend (service role / postgres connection, unaffected by these
-- grants). Applies even to SELECT: a token is a bearer secret and an
-- email is PII, neither belongs in a PostgREST-reachable table.
REVOKE ALL ON public.invitations FROM anon, authenticated;

-- Defence in depth, matching every other table in the schema: grants are the
-- boundary, RLS with zero policies is the backstop if one is ever granted by
-- accident. The backend connects as the table owner and is unaffected.
--
-- Added 2026-08-06, when applying this migration: it was written on
-- 2026-07-07 but never reached production, so the invitations endpoints have
-- been failing on a missing relation ever since. Found by diffing the
-- SQLAlchemy model tables against information_schema.
ALTER TABLE public.invitations ENABLE ROW LEVEL SECURITY;
