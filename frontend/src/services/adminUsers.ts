import api from "./api"
import type { User } from "@/types"

/**
 * Admin-only user management endpoints exposed at /users/admin/*.
 * Kept separate from usersService (which handles the current user's profile)
 * because the authorisation scope and risk profile are very different.
 */
export const adminUsersService = {
  async getAllUsers(): Promise<User[]> {
    const response = await api.get<User[]>("/users/admin/users")
    return response.data
  },

  async updateUserRole(userId: string, role: string): Promise<void> {
    await api.put(`/users/admin/users/${userId}/role`, null, { params: { role } })
  },

  async bulkUpdateUserRoles(
    userIds: string[],
    role: string,
  ): Promise<{ updated: number; role: string }> {
    const response = await api.put<{ updated: number; role: string }>(
      "/users/admin/users/bulk-role",
      { user_ids: userIds, role },
    )
    return response.data
  },

  async adminDeleteUser(userId: string): Promise<void> {
    await api.delete(`/users/admin/users/${userId}`)
  },

  async restoreUser(userId: string): Promise<void> {
    await api.post(`/users/admin/users/${userId}/restore`)
  },
}
