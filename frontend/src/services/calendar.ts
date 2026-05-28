import api from "./api"
import { cached, cacheInvalidate, cacheInvalidatePrefix, CACHE_TTL } from "@/lib/cache"
import type { CalendarEvent, CourseEvent } from "@/types"

export const calendarService = {
  async getCalendarEvents(courseId?: string): Promise<CalendarEvent[]> {
    return cached(`calendar:events:${courseId ?? "all"}`, CACHE_TTL.ONE_MINUTE, async () => {
      const params = courseId ? { course_id: courseId } : undefined
      const response = await api.get<CalendarEvent[]>("/calendar/events", { params })
      return response.data
    })
  },

  async getCourseEvents(courseId: string): Promise<CourseEvent[]> {
    return cached(`calendar:course-events:${courseId}`, CACHE_TTL.TWO_MINUTES, async () => {
      const response = await api.get<CourseEvent[]>(`/courses/${courseId}/events`)
      return response.data
    })
  },

  /**
   * Teacher-only fetch returning source-language event titles +
   * descriptions, used by the calendar event editor. Mirrors the
   * `?source=1` pattern from `getCourseForEdit` /
   * `getAnnouncementsForEdit`: bypass the locale overlay so the
   * teacher edits their own typed text, not the MT version.
   *
   * Bypasses the `calendar:course-events:{id}` cache to keep the
   * student-facing localized payload separate from the teacher-only
   * source payload.
   */
  async getCourseEventsForEdit(courseId: string): Promise<CourseEvent[]> {
    const response = await api.get<CourseEvent[]>(`/courses/${courseId}/events`, {
      params: { source: 1 },
    })
    return response.data
  },

  async createCourseEvent(
    courseId: string,
    data: {
      title: string
      description?: string
      event_type?: string
      event_date: string
    },
  ): Promise<CourseEvent> {
    const response = await api.post<CourseEvent>(`/courses/${courseId}/events`, data)
    cacheInvalidate(`calendar:course-events:${courseId}`)
    cacheInvalidatePrefix("calendar:events:")
    return response.data
  },

  async updateCourseEvent(
    courseId: string,
    eventId: string,
    data: {
      title?: string
      description?: string
      event_type?: string
      event_date?: string
    },
  ): Promise<CourseEvent> {
    const response = await api.put<CourseEvent>(
      `/courses/${courseId}/events/${eventId}`,
      data,
    )
    cacheInvalidate(`calendar:course-events:${courseId}`)
    cacheInvalidatePrefix("calendar:events:")
    return response.data
  },

  async deleteCourseEvent(courseId: string, eventId: string): Promise<void> {
    await api.delete(`/courses/${courseId}/events/${eventId}`)
    cacheInvalidate(`calendar:course-events:${courseId}`)
    cacheInvalidatePrefix("calendar:events:")
  },
}
