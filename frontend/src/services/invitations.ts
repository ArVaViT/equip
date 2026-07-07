import api from "./api"
import type { Invitation, InvitationRole, InvitationStatus } from "@/types"

export interface InvitationPreview {
  email: string
  role: InvitationRole
  status: InvitationStatus
  is_expired: boolean
}

/**
 * Admin invite-by-email endpoints at /invitations/*, plus the two
 * routes the accept-invite page uses (public preview, authenticated
 * accept). Kept separate from adminUsersService the same way that
 * module is separate from usersService -- different auth scope
 * (admin-only create/list vs. public/self-serve accept).
 */
export const invitationsService = {
  async createInvitation(email: string, role: InvitationRole): Promise<Invitation> {
    const response = await api.post<Invitation>("/invitations", { email, role })
    return response.data
  },

  async listInvitations(params?: {
    role?: InvitationRole
    status?: InvitationStatus
  }): Promise<Invitation[]> {
    const response = await api.get<Invitation[]>("/invitations", { params })
    return response.data
  },

  async previewInvitation(token: string): Promise<InvitationPreview> {
    const response = await api.get<InvitationPreview>(`/invitations/token/${encodeURIComponent(token)}`)
    return response.data
  },

  async acceptInvitation(token: string): Promise<{ role: InvitationRole }> {
    const response = await api.post<{ role: InvitationRole }>("/invitations/accept", { token })
    return response.data
  },
}
