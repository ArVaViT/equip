import api from "./api"
import { cached, cacheInvalidate, cacheInvalidatePrefix, CACHE_TTL } from "@/lib/cache"
import type { Course, Module, Chapter } from "@/types"

import { adminUsersService } from "./adminUsers"
import { announcementsService } from "./announcements"
import { assignmentsService } from "./assignments"
import { auditService } from "./audit"
import { blocksService } from "./blocks"
import { calendarService } from "./calendar"
import { certificatesService } from "./certificates"
import { cohortsService } from "./cohorts"
import { enrollmentsService } from "./enrollments"
import { gradesService } from "./grades"
import { notificationsService } from "./notifications"
import { progressService } from "./progress"
import { quizzesService } from "./quizzes"
import { reviewsService } from "./reviews"
import { analyticsService } from "./analytics"

/**
 * Course, module, and chapter CRUD. All three hang off the same course URL
 * and share one cache-invalidation graph (`courses:detail:*`,
 * `courses:module:*`), so they stay together. Every other domain lives in
 * its own service file.
 *
 * Chapters are addressed `/courses/:id/chapters/:cid` — a lesson belongs to
 * the course, and the module that groups it is a field on the lesson rather
 * than part of its address. The older `/modules/:mid/chapters/:cid` calls
 * are still here, and still work, until the screens have moved off them.
 *
 * `coursesService` is also re-exported as a facade that spreads every
 * domain service so legacy call sites like `coursesService.getChapterQuiz`
 * keep working during migration. New code should import the specific
 * per-domain service (e.g. `import { quizzesService } from "./quizzes"`).
 */

// ─── Cache invalidation helpers ─────────────────────────────────────────
// Mutations to courses/modules/chapters have to nudge several keys in
// lockstep — these three helpers centralize the "graph" so the picture
// of which mutation invalidates what is in one place.

/** Course list pages (search-scoped and teacher-scoped). Touched by any course mutation. */
function invalidateCourseLists(): void {
  cacheInvalidatePrefix("courses:list:")
  cacheInvalidate("courses:teacher")
}

/** A specific course's detail and a specific module's snapshot. Touched by module mutations. */
function invalidateModuleScope(courseId: string, moduleId: string): void {
  cacheInvalidate(`courses:detail:${courseId}`)
  cacheInvalidate(`courses:module:${courseId}:${moduleId}`)
}

/**
 * A course's detail and every module snapshot under it.
 *
 * This is the scope of a **chapter** mutation, and of anything that wipes a
 * whole course. Chapters used to invalidate the (course, module) pair, which
 * is now wrong twice over: a lesson in no module has no pair to name, and a
 * lesson moving between modules leaves the module it *left* holding a stale
 * copy of it. The course is the unit a chapter belongs to, so the course is
 * the unit that goes stale.
 */
function invalidateCourseScope(courseId: string): void {
  cacheInvalidate(`courses:detail:${courseId}`)
  cacheInvalidatePrefix(`courses:module:${courseId}:`)
}

const courseCrud = {
  async getCourses(search?: string, opts?: { skip?: number; limit?: number }): Promise<Course[]> {
    const skip = opts?.skip ?? 0
    const limit = opts?.limit
    return cached(`courses:list:${search ?? ""}:${skip}:${limit ?? ""}`, CACHE_TTL.TWO_MINUTES, async () => {
      const params: Record<string, string | number> = {}
      if (search) params.search = search
      if (skip) params.skip = skip
      if (limit !== undefined) params.limit = limit
      const response = await api.get<Course[]>("/courses", { params })
      return response.data
    })
  },

  async getCourse(id: string): Promise<Course> {
    return cached(`courses:detail:${id}`, CACHE_TTL.THREE_MINUTES, async () => {
      const response = await api.get<Course>(`/courses/${id}`)
      return response.data
    })
  },

  /**
   * Editor-only fetch: forces the API to return source-language columns
   * regardless of the viewer's `preferred_locale`. Use from `CourseEditor` /
   * `useCourseData` so a teacher editing their RU course in EN UI doesn't
   * see the EN translation in InlineEdit fields (and PATCH it back into the
   * source `title` column).
   *
   * Owner / admin only — the backend returns 403 for anyone else, so this
   * function is safe to call from teacher-only routes.
   *
   * Intentionally bypasses the `courses:detail:{id}` cache: the student-
   * facing read populates the same key with the localized payload, and we
   * don't want one view to clobber the other.
   */
  async getCourseForEdit(id: string): Promise<Course> {
    const response = await api.get<Course>(`/courses/${id}`, {
      params: { source: 1 },
    })
    return response.data
  },

  async getTeacherCourses(): Promise<Course[]> {
    return cached("courses:teacher", CACHE_TTL.ONE_MINUTE, async () => {
      const response = await api.get<Course[]>("/courses/my")
      return response.data
    })
  },

  async createCourse(
    data: { title: string; description?: string; image_url?: string },
  ): Promise<Course> {
    const response = await api.post<Course>("/courses", data)
    invalidateCourseLists()
    return response.data
  },

  async updateCourse(
    id: string,
    data: {
      title?: string
      description?: string | null
      image_url?: string | null
      status?: string
      access_mode?: "public" | "institute"
      enrollment_start?: string | null
      enrollment_end?: string | null
    },
  ): Promise<Course> {
    const response = await api.put<Course>(`/courses/${id}`, data)
    cacheInvalidate(`courses:detail:${id}`)
    invalidateCourseLists()
    return response.data
  },

  async deleteCourse(id: string): Promise<void> {
    await api.delete(`/courses/${id}`)
    invalidateCourseScope(id)
    invalidateCourseLists()
  },

  async getTrashedCourses(): Promise<Course[]> {
    const response = await api.get<Course[]>("/courses/my/trash")
    return response.data
  },

  async restoreCourse(id: string): Promise<Course> {
    const response = await api.post<Course>(`/courses/${id}/restore`)
    invalidateCourseLists()
    return response.data
  },

  async permanentlyDeleteCourse(id: string): Promise<void> {
    await api.delete(`/courses/${id}/permanent`)
    invalidateCourseScope(id)
    invalidateCourseLists()
  },

  async cloneCourse(id: string): Promise<Course> {
    const response = await api.post<Course>(`/courses/${id}/clone`)
    invalidateCourseLists()
    return response.data
  },

  async getModule(courseId: string, moduleId: string): Promise<Module> {
    return cached(`courses:module:${courseId}:${moduleId}`, CACHE_TTL.THREE_MINUTES, async () => {
      const response = await api.get<Module>(`/courses/${courseId}/modules/${moduleId}`)
      return response.data
    })
  },

  /**
   * Editor-only fetch: see `getCourseForEdit`. Forces source-language
   * columns from the module-detail endpoint so `ModuleEditor` and
   * `ChapterEditor` (which loads its chapter list via the module response)
   * don't see translation overlays in editable fields.
   */
  async getModuleForEdit(courseId: string, moduleId: string): Promise<Module> {
    const response = await api.get<Module>(
      `/courses/${courseId}/modules/${moduleId}`,
      { params: { source: 1 } },
    )
    return response.data
  },

  async createModule(
    courseId: string,
    data: { title: string; description?: string; order_index?: number },
  ): Promise<Module> {
    const response = await api.post<Module>(`/courses/${courseId}/modules`, data)
    invalidateCourseScope(courseId)
    return response.data
  },

  async updateModule(
    courseId: string,
    moduleId: string,
    data: {
      title?: string
      description?: string
      order_index?: number
      due_date?: string | null
    },
  ): Promise<Module> {
    const response = await api.put<Module>(
      `/courses/${courseId}/modules/${moduleId}`,
      data,
    )
    invalidateModuleScope(courseId, moduleId)
    return response.data
  },

  async deleteModule(courseId: string, moduleId: string): Promise<void> {
    await api.delete(`/courses/${courseId}/modules/${moduleId}`)
    invalidateModuleScope(courseId, moduleId)
  },

  // ─── Chapters, addressed by their course ──────────────────────────────
  // A lesson belongs to a course; a module only groups it. These four speak
  // that shape — no module in the address, and `module_id` is a property of
  // the lesson that a `PUT` can set or clear. Prefer them everywhere; the
  // module-shaped trio below is what the screens still call, and goes when
  // the last of them has moved.

  /**
   * Write a lesson straight into the course, grouped by nothing.
   *
   * The body deliberately has no `module_id`: the create endpoint rejects
   * unknown keys, and a lesson that should start life inside a module is
   * created here and then moved with `updateCourseChapter`.
   */
  async createCourseChapter(
    courseId: string,
    data: { title: string; order_index?: number; chapter_type?: string },
  ): Promise<Chapter> {
    const response = await api.post<Chapter>(`/courses/${courseId}/chapters`, data)
    invalidateCourseScope(courseId)
    return response.data
  },

  /**
   * One lesson by its id — the whole reason this exists. Reaching a lesson
   * used to mean fetching the module around it and picking the lesson out of
   * the list, which asks for a module the lesson may not have.
   *
   * Editor-only, like `getCourseForEdit` and `getModuleForEdit`: the endpoint
   * is owner/admin-gated and answers in the course's source language, so a
   * teacher editing a RU course in an EN interface binds their fields to the
   * Russian they wrote and not to its translation. Uncached for the same
   * reason those two are.
   */
  async getChapterForEdit(courseId: string, chapterId: string): Promise<Chapter> {
    const response = await api.get<Chapter>(
      `/courses/${courseId}/chapters/${chapterId}`,
    )
    return response.data
  },

  /**
   * Edit a lesson, including where it sits.
   *
   * `module_id` is three-valued and the difference matters on the wire:
   *   - key absent — the grouping is left alone,
   *   - `"<module id>"` — the lesson moves into that module (of this course;
   *     a module belonging to another course is refused),
   *   - `null` — the lesson comes out of its module and sits in the course.
   * `undefined` drops out of the JSON body, so it reads as "absent" — which
   * is why "leave it alone" must never be written as an explicit `null`.
   */
  async updateCourseChapter(
    courseId: string,
    chapterId: string,
    data: {
      title?: string
      order_index?: number
      chapter_type?: string
      requires_completion?: boolean
      is_locked?: boolean
      module_id?: string | null
    },
  ): Promise<Chapter> {
    const response = await api.put<Chapter>(
      `/courses/${courseId}/chapters/${chapterId}`,
      data,
    )
    invalidateCourseScope(courseId)
    return response.data
  },

  async deleteCourseChapter(courseId: string, chapterId: string): Promise<void> {
    await api.delete(`/courses/${courseId}/chapters/${chapterId}`)
    invalidateCourseScope(courseId)
  },

  // ─── Chapters, addressed through their module (legacy) ────────────────
  // Kept working while the screens migrate. Same endpoints as before; only
  // the invalidation changed, to the course — see `invalidateCourseScope`.

  async createChapter(
    courseId: string,
    moduleId: string,
    data: { title: string; order_index?: number; chapter_type?: string },
  ): Promise<Chapter> {
    const response = await api.post<Chapter>(
      `/courses/${courseId}/modules/${moduleId}/chapters`,
      data,
    )
    invalidateCourseScope(courseId)
    return response.data
  },

  async updateChapter(
    courseId: string,
    moduleId: string,
    chapterId: string,
    data: {
      title?: string
      order_index?: number
      chapter_type?: string
      requires_completion?: boolean
      is_locked?: boolean
    },
  ): Promise<Chapter> {
    const response = await api.put<Chapter>(
      `/courses/${courseId}/modules/${moduleId}/chapters/${chapterId}`,
      data,
    )
    invalidateCourseScope(courseId)
    return response.data
  },

  async deleteChapter(
    courseId: string,
    moduleId: string,
    chapterId: string,
  ): Promise<void> {
    await api.delete(
      `/courses/${courseId}/modules/${moduleId}/chapters/${chapterId}`,
    )
    invalidateCourseScope(courseId)
  },
}

/**
 * Backwards-compatible aggregate. Prefer the per-domain services for new code
 * — this facade exists solely so the long-lived `coursesService.*` call sites
 * across the app keep working while we migrate them file-by-file.
 *
 * The individual domain services are re-exported from their own modules
 * (e.g. `import { quizzesService } from "@/services/quizzes"`); routing
 * every one through this file would just add an import hop.
 */
export const coursesService = {
  ...courseCrud,
  ...adminUsersService,
  ...announcementsService,
  ...assignmentsService,
  ...auditService,
  ...blocksService,
  ...calendarService,
  ...certificatesService,
  ...cohortsService,
  ...enrollmentsService,
  ...gradesService,
  ...notificationsService,
  ...progressService,
  ...quizzesService,
  ...reviewsService,
  ...analyticsService,
}
