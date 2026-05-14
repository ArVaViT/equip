import api from "./api"
import { cacheGet, cacheSet, cacheInvalidate, cacheInvalidatePrefix } from "@/lib/cache"
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
const courseCrud = {
  async getCourses(search?: string): Promise<Course[]> {
    const key = `courses:list:${search ?? ""}`
    const cached = cacheGet<Course[]>(key)
    if (cached) return cached
    const params = search ? { search } : undefined
    const response = await api.get<Course[]>("/courses", { params })
    cacheSet(key, response.data, 2 * 60 * 1000)
    return response.data
  },

  async getCourse(id: string): Promise<Course> {
    const key = `courses:detail:${id}`
    const cached = cacheGet<Course>(key)
    if (cached) return cached
    const response = await api.get<Course>(`/courses/${id}`)
    cacheSet(key, response.data, 3 * 60 * 1000)
    return response.data
  },

  async getTeacherCourses(): Promise<Course[]> {
    const key = "courses:teacher"
    const cached = cacheGet<Course[]>(key)
    if (cached) return cached
    const response = await api.get<Course[]>("/courses/my")
    cacheSet(key, response.data, 60 * 1000)
    return response.data
  },

  async createCourse(
    data: { title: string; description?: string; image_url?: string },
  ): Promise<Course> {
    const response = await api.post<Course>("/courses", data)
    cacheInvalidatePrefix("courses:list:")
    cacheInvalidate("courses:teacher")
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
    cacheInvalidatePrefix("courses:list:")
    cacheInvalidate("courses:teacher")
    return response.data
  },

  async deleteCourse(id: string): Promise<void> {
    await api.delete(`/courses/${id}`)
    cacheInvalidate(`courses:detail:${id}`)
    cacheInvalidatePrefix("courses:list:")
    cacheInvalidatePrefix(`courses:module:${id}:`)
    cacheInvalidate("courses:teacher")
  },

  async getTrashedCourses(): Promise<Course[]> {
    const response = await api.get<Course[]>("/courses/my/trash")
    return response.data
  },

  async restoreCourse(id: string): Promise<Course> {
    const response = await api.post<Course>(`/courses/${id}/restore`)
    cacheInvalidatePrefix("courses:list:")
    cacheInvalidate("courses:teacher")
    return response.data
  },

  async permanentlyDeleteCourse(id: string): Promise<void> {
    await api.delete(`/courses/${id}/permanent`)
    cacheInvalidate(`courses:detail:${id}`)
    cacheInvalidatePrefix("courses:list:")
    cacheInvalidatePrefix(`courses:module:${id}:`)
    cacheInvalidate("courses:teacher")
  },

  async cloneCourse(id: string): Promise<Course> {
    const response = await api.post<Course>(`/courses/${id}/clone`)
    cacheInvalidatePrefix("courses:list:")
    cacheInvalidate("courses:teacher")
    return response.data
  },

  async getModule(courseId: string, moduleId: string): Promise<Module> {
    const key = `courses:module:${courseId}:${moduleId}`
    const cached = cacheGet<Module>(key)
    if (cached) return cached
    const response = await api.get<Module>(`/courses/${courseId}/modules/${moduleId}`)
    cacheSet(key, response.data, 3 * 60 * 1000)
    return response.data
  },

  async createModule(
    courseId: string,
    data: { title: string; description?: string; order_index?: number },
  ): Promise<Module> {
    const response = await api.post<Module>(`/courses/${courseId}/modules`, data)
    cacheInvalidate(`courses:detail:${courseId}`)
    cacheInvalidatePrefix(`courses:module:${courseId}:`)
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
    cacheInvalidate(`courses:detail:${courseId}`)
    cacheInvalidate(`courses:module:${courseId}:${moduleId}`)
    return response.data
  },

  async deleteModule(courseId: string, moduleId: string): Promise<void> {
    await api.delete(`/courses/${courseId}/modules/${moduleId}`)
    cacheInvalidate(`courses:detail:${courseId}`)
    cacheInvalidate(`courses:module:${courseId}:${moduleId}`)
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
    cacheInvalidate(`courses:detail:${courseId}`)
    cacheInvalidate(`courses:module:${courseId}:${moduleId}`)
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
    cacheInvalidate(`courses:detail:${courseId}`)
    cacheInvalidate(`courses:module:${courseId}:${moduleId}`)
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
    cacheInvalidate(`courses:detail:${courseId}`)
    cacheInvalidate(`courses:module:${courseId}:${moduleId}`)
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
