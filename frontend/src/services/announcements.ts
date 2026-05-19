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

  // Banner-only feed. ``getAnnouncements()`` returns every row visible
  // to the user (enrolled + owned + site-wide), so the banner used to
  // pull dozens of course-scoped rows just to ``find`` the site-wide
  // one. ``global_only=true`` lets the backend filter to ``course_id
  // IS NULL`` so the wire payload matches what the banner renders.
  async getGlobalAnnouncements(): Promise<Announcement[]> {
    return cached(`announcements:global-only`, CACHE_TTL.TWO_MINUTES, async () => {
      const response = await api.get<Announcement[]>("/announcements", {
        params: { global_only: true, limit: 10 },
      })
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
    if (!data.course_id) cacheInvalidate(`announcements:global-only`)
    if (data.course_id) cacheInvalidate(`announcements:course:${data.course_id}`)
    return response.data
  },

  async deleteAnnouncement(id: string): Promise<void> {
    await api.delete(`/announcements/${id}`)
    cacheInvalidatePrefix(`announcements:`)
  },
}
