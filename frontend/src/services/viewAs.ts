import api from "./api"
import type { ViewAs } from "@/lib/viewAs"

/** Start / end a read-only "view as" (backend ``admin_view_as``). Sent as the admin themself. */
export const viewAsService = {
  async start(email: string, reason: string): Promise<ViewAs> {
    const { data } = await api.post<ViewAs>("/admin/view-as", { email, reason }, { skipViewAs: true })
    return data
  },
  async end(id: string): Promise<void> {
    await api.post(`/admin/view-as/${id}/end`, null, { skipViewAs: true })
  },
}
