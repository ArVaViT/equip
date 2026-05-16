import api from "./api"
import { cached, cacheInvalidate, cacheInvalidatePrefix, CACHE_TTL } from "@/lib/cache"
import type { Announcement } from "@/types"

export const announcementsService = {
  async getAnnouncements(courseId?: string): Promise<Announcement[]> {
    const key = courseId ? `announcements:course:${courseId}` : `announcements:global`
    return cached(key, CACHE_TTL.TWO_MINUTES, async () => {
      const params = courseId ? { course_id: courseId } : undefined
      const response = await api.get<Announcement[]>("/announcements", { params })
      return response.data
    })
  },

  async createAnnouncement(data: {
    title: string
    content: string
    course_id?: string
  }): Promise<Announcement> {
    const response = await api.post<Announcement>("/announcements", data)
    cacheInvalidate(`announcements:global`)
    if (data.course_id) cacheInvalidate(`announcements:course:${data.course_id}`)
    return response.data
  },

  async deleteAnnouncement(id: string): Promise<void> {
    await api.delete(`/announcements/${id}`)
    cacheInvalidatePrefix(`announcements:`)
  },
}
