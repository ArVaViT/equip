import api from "./api"
import { cached, cacheInvalidate, cacheInvalidatePrefix, CACHE_TTL } from "@/lib/cache"
import type { CalendarEvent, CourseEvent } from "@/types"

/** Which occurrences of a weekly series an edit or a delete reaches. */
export type SeriesScope = "this" | "following" | "all"

/** The body of a new event or an edit; mirrors ``CourseEventCreate`` /
 *  ``CourseEventUpdate`` on the server. `null` clears a field on an edit. */
export interface CourseEventPayload {
  title?: string
  description?: string
  event_type?: string
  event_date?: string
  meeting_url?: string | null
  recording_url?: string | null
  duration_minutes?: number | null
  /** New events only: repeat every `every_weeks` weeks through `until`
   *  (a `YYYY-MM-DD` day in `time_zone`). */
  repeat?: { every_weeks: number; until: string; time_zone: string }
  /** Edits only: the zone a series move is measured in. */
  time_zone?: string
}

export interface IcalFeed {
  feed_url: string
  expires_at: string
}

export const calendarService = {
  /**
   * A personal subscription link to the reader's calendar. Every call
   * issues a new link and switches the previous one off (the server keeps
   * only a floor, `calendar_ical_min_iat`), so it is called on an explicit
   * "create a link", never on opening a dialog.
   */
  async issueIcalFeed(): Promise<IcalFeed> {
    const response = await api.post<IcalFeed>("/calendar/ical/token")
    return response.data
  },

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
    data: CourseEventPayload & { title: string; event_date: string },
  ): Promise<CourseEvent> {
    const response = await api.post<CourseEvent>(`/courses/${courseId}/events`, data)
    cacheInvalidate(`calendar:course-events:${courseId}`)
    cacheInvalidatePrefix("calendar:events:")
    return response.data
  },

  async updateCourseEvent(
    courseId: string,
    eventId: string,
    data: CourseEventPayload,
    scope: SeriesScope = "this",
  ): Promise<CourseEvent> {
    const response = await api.put<CourseEvent>(
      `/courses/${courseId}/events/${eventId}`,
      data,
      scope === "this" ? undefined : { params: { scope } },
    )
    cacheInvalidate(`calendar:course-events:${courseId}`)
    cacheInvalidatePrefix("calendar:events:")
    return response.data
  },

  async deleteCourseEvent(courseId: string, eventId: string, scope: SeriesScope = "this"): Promise<void> {
    await api.delete(
      `/courses/${courseId}/events/${eventId}`,
      scope === "this" ? undefined : { params: { scope } },
    )
    cacheInvalidate(`calendar:course-events:${courseId}`)
    cacheInvalidatePrefix("calendar:events:")
  },
}
