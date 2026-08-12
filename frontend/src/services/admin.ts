import api from "./api"
import type { OrgSettings, OrgSettingsUpdate } from "@/types"

/**
 * What the school decides about itself (D1).
 *
 * Admin-only on the server. Every field here was read-only until this shipped:
 * putting a school's name on its own ведомость meant an UPDATE run by hand
 * against the production database.
 */
export const adminService = {
  async getOrgSettings(): Promise<OrgSettings> {
    const response = await api.get<OrgSettings>("/admin/org-settings")
    return response.data
  },

  /** Partial: whatever is sent is written, the rest is left alone. Sending a
   *  whole object would let a typo fix wipe the school's grading scale. */
  async updateOrgSettings(patch: OrgSettingsUpdate): Promise<OrgSettings> {
    const response = await api.put<OrgSettings>("/admin/org-settings", patch)
    return response.data
  },
}
