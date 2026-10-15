import api from "./api"
import type { Invitation, InvitationRole, InvitationStatus } from "@/types"
import type { SupportedLocale } from "@/i18n/config"

/** What the acceptance actually did, so the page can go where it leads. */
export interface AcceptedInvitation {
  role: InvitationRole
  scope: "platform" | "organization" | "course"
  enrolled_course_id: string | null
  /** The address the account holds — what to sign in with after registering. */
  email: string
}

/** Why a link admits nobody now. Mirrors `UnusableReasonLiteral` on the server. */
export type InvitationUnusableReason = "expired" | "used" | "revoked" | "inviter_left" | "course_gone"

export interface InvitationPreview {
  email: string
  role: InvitationRole
  scope: "platform" | "organization" | "course"
  /** In the reader's language, or null — never another language's title. */
  course_title: string | null
  /** Who is inviting; null for a platform invitation. */
  organization_name: string | null
  status: InvitationStatus
  is_expired: boolean
  /** Null while the link still admits its person. */
  unusable_reason: InvitationUnusableReason | null
  /** The invited address already has a confirmed account: sign in, not sign up. */
  has_account: boolean
}

/**
 * Admin invite-by-email endpoints at /invitations/*, plus the two
 * routes the accept-invite page uses (public preview, authenticated
 * accept). Kept separate from adminUsersService the same way that
 * module is separate from usersService -- different auth scope
 * (admin-only create/list vs. public/self-serve accept).
 */
export const invitationsService = {
  /**
   * Write (or resend) an invitation.
   *
   * ``ageAttested`` is the sender's statement that this person is thirteen
   * or older. It has no default and the server refuses ``false`` exactly as
   * firmly as it refuses a missing field — an attestation nobody made is not
   * an attestation, and a default here would make it one.
   */
  async createInvitation(
    email: string,
    role: InvitationRole,
    ageAttested: boolean,
    /** What the invitation grants. Omitted: the school's — the server's
     *  default. A resend passes the row's own, or a platform invitation
     *  would come back as a school one. */
    target?: { scope: NonNullable<Invitation["scope"]>; courseId?: string | null },
  ): Promise<Invitation> {
    const response = await api.post<Invitation>("/invitations", {
      email,
      role,
      age_attested: ageAttested,
      ...(target ? { scope: target.scope, course_id: target.courseId ?? null } : {}),
    })
    return response.data
  },

  async listInvitations(params?: {
    role?: InvitationRole
    status?: InvitationStatus
  }): Promise<Invitation[]> {
    const response = await api.get<Invitation[]>("/invitations", { params })
    return response.data
  },

  /**
   * Withdraw a pending invitation so its link stops working.
   *
   * `revoked` was a legal status from the first migration and the accept
   * path already refused anything that was not `pending`, but there was no
   * route to set it — so an invitation sent to the wrong address stayed
   * live for seven days, carrying a teacher role with it.
   */
  async revokeInvitation(id: string): Promise<Invitation> {
    const response = await api.delete<Invitation>(`/invitations/${encodeURIComponent(id)}`)
    return response.data
  },

  /**
   * The token goes in the body. As a path segment
   * (`GET /invitations/token/<token>`) it was written into the backend's
   * access log and the hosting platform's request log on every visit.
   */
  async previewInvitation(token: string): Promise<InvitationPreview> {
    const response = await api.post<InvitationPreview>("/invitations/preview", { token })
    return response.data
  },

  async acceptInvitation(token: string): Promise<AcceptedInvitation> {
    const response = await api.post<AcceptedInvitation>("/invitations/accept", { token })
    return response.data
  },

  /**
   * Create the invited person's account from the link and accept it, in one
   * request. No email: the account is made for the address the invitation
   * was sent to, and it is confirmed already — the link proved the mailbox,
   * so no second email follows. The caller signs in with `password` next.
   */
  async registerByInvitation(
    token: string,
    fullName: string,
    password: string,
    locale: SupportedLocale,
  ): Promise<AcceptedInvitation> {
    const response = await api.post<AcceptedInvitation>("/invitations/register", {
      token,
      full_name: fullName,
      password,
      locale,
    })
    return response.data
  },
}
