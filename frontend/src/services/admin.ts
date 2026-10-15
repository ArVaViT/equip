import api from "./api"
import type { OrgSettings, OrgSettingsUpdate } from "@/types"

const orgHeader = (organizationId?: string) =>
  organizationId ? { "X-Organization-Id": organizationId } : undefined

/**
 * What the school decides about itself (D1).
 *
 * Admin-only on the server. Every field here was read-only until this shipped:
 * putting a school's name on its own ведомость meant an UPDATE run by hand
 * against the production database.
 */
export const adminService = {
  /** ``organizationId`` names the school (platform staff, from its row on the
   *  organizations tab); without it the server picks the caller's own. */
  async getOrgSettings(organizationId?: string): Promise<OrgSettings> {
    const response = await api.get<OrgSettings>("/admin/org-settings", { headers: orgHeader(organizationId) })
    return response.data
  },

  /** Partial: whatever is sent is written, the rest is left alone. Sending a
   *  whole object would let a typo fix wipe the school's grading scale. */
  async updateOrgSettings(patch: OrgSettingsUpdate, organizationId?: string): Promise<OrgSettings> {
    const response = await api.put<OrgSettings>("/admin/org-settings", patch, { headers: orgHeader(organizationId) })
    return response.data
  },
}
