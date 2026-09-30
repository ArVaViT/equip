import api from "./api"
import { cached, cacheInvalidate } from "@/lib/cache"
import type { Notification, NotificationListResponse } from "@/types"

const UNREAD_KEY = "notifications:unread-count"

export const notificationsService = {
  async getNotifications(page: number = 1): Promise<NotificationListResponse> {
    const response = await api.get<NotificationListResponse>("/notifications", {
      params: { page },
    })
    return response.data
  },

  /**
   * The header renders a bell for phones and one for desktop (CSS hides
   * one), and each polled on its own: two requests per interval for one
   * number. Held for a few seconds, the second bell reads the first one's
   * answer; anything that changes the count drops it.
   */
  async getUnreadCount(): Promise<number> {
    return cached(UNREAD_KEY, 5_000, async () => {
      const response = await api.get<{ count: number }>("/notifications/unread-count")
      return response.data.count
    })
  },

  async markAsRead(id: string): Promise<Notification> {
    const response = await api.patch<Notification>(`/notifications/${id}/read`)
    cacheInvalidate(UNREAD_KEY)
    return response.data
  },

  async markAllAsRead(): Promise<void> {
    await api.post("/notifications/read-all")
    cacheInvalidate(UNREAD_KEY)
  },

  async deleteNotification(id: string): Promise<void> {
    await api.delete(`/notifications/${id}`)
    cacheInvalidate(UNREAD_KEY)
  },
}
