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
 * Course, module, and chapter CRUD. These three entities share the same
 * nested URL structure (`/courses/:id/modules/:mid/chapters/:cid`) and the
 * same cache-invalidation graph (`courses:detail:*`, `courses:module:*`),
 * so they stay together. Every other domain lives in its own service file.
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

/** A specific course's detail and a specific module's snapshot. Touched by module/chapter mutations. */
function invalidateModuleScope(courseId: string, moduleId: string): void {
  cacheInvalidate(`courses:detail:${courseId}`)
  cacheInvalidate(`courses:module:${courseId}:${moduleId}`)
}

/** All modules under a course plus the course's detail. Used when wiping a whole course. */
function invalidateAllModulesUnderCourse(courseId: string): void {
  cacheInvalidate(`courses:detail:${courseId}`)
  cacheInvalidatePrefix(`courses:module:${courseId}:`)
}

const courseCrud = {
  async getCourses(search?: string): Promise<Course[]> {
    return cached(`courses:list:${search ?? ""}`, CACHE_TTL.TWO_MINUTES, async () => {
      const params = search ? { search } : undefined
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
    invalidateAllModulesUnderCourse(id)
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
    invalidateAllModulesUnderCourse(id)
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
    invalidateAllModulesUnderCourse(courseId)
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

  async createChapter(
    courseId: string,
    moduleId: string,
    data: { title: string; order_index?: number; chapter_type?: string },
  ): Promise<Chapter> {
    const response = await api.post<Chapter>(
      `/courses/${courseId}/modules/${moduleId}/chapters`,
      data,
    )
    invalidateModuleScope(courseId, moduleId)
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
    invalidateModuleScope(courseId, moduleId)
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
    invalidateModuleScope(courseId, moduleId)
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
