import api from "./api"
import { cached, cacheInvalidatePrefix, CACHE_TTL } from "@/lib/cache"
import type { Cohort } from "@/types"

export interface CohortStudent {
  user_id: string
  full_name: string | null
  email: string
  per_course: Record<
    string,
    {
      enrollment_id: string
      enrolled_at: string | null
      progress: number
    }
  >
}

export interface CreateCohortBody {
  name: string
  start_date: string
  end_date: string
  enrollment_start?: string | null
  enrollment_end?: string | null
  max_students?: number | null
}

export interface UpdateCohortBody {
  name?: string
  start_date?: string
  end_date?: string
  enrollment_start?: string | null
  enrollment_end?: string | null
  status?: "upcoming" | "active" | "completed"
  max_students?: number | null
}

/**
 * Cohort service — read + admin write surfaces per ADR-010.
 *
 * The public-ish read (`getCourseCohorts`) is used by the catalog
 * enroll dialog. Everything else (`listCohorts`, create/update/delete,
 * attach/detach course, add/remove student, complete) is admin-only
 * and consumed by `pages/Admin/cohorts/*`.
 */
function invalidateCourseLists() {
  cacheInvalidatePrefix("cohorts:course:")
}

export const cohortsService = {
  async getCourseCohorts(courseId: string): Promise<Cohort[]> {
    return cached(`cohorts:course:${courseId}`, CACHE_TTL.TWO_MINUTES, async () => {
      const response = await api.get<Cohort[]>(`/cohorts/course/${courseId}`)
      return response.data
    })
  },

  // -------------------- admin: cohort CRUD --------------------

  async listCohorts(statusFilter?: UpdateCohortBody["status"]): Promise<Cohort[]> {
    const url = statusFilter ? `/cohorts?status=${statusFilter}` : "/cohorts"
    const response = await api.get<Cohort[]>(url)
    return response.data
  },

  async getCohort(cohortId: string): Promise<Cohort> {
    const response = await api.get<Cohort>(`/cohorts/${cohortId}`)
    return response.data
  },

  async createCohort(body: CreateCohortBody): Promise<Cohort> {
    const response = await api.post<Cohort>("/cohorts", body)
    invalidateCourseLists()
    return response.data
  },

  async updateCohort(cohortId: string, body: UpdateCohortBody): Promise<Cohort> {
    const response = await api.patch<Cohort>(`/cohorts/${cohortId}`, body)
    invalidateCourseLists()
    return response.data
  },

  async deleteCohort(cohortId: string): Promise<void> {
    await api.delete(`/cohorts/${cohortId}`)
    invalidateCourseLists()
  },

  async completeCohort(cohortId: string): Promise<Cohort> {
    const response = await api.post<Cohort>(`/cohorts/${cohortId}/complete`)
    invalidateCourseLists()
    return response.data
  },

  // ----------------- admin: cohort x courses ------------------

  async attachCourseToCohort(cohortId: string, courseId: string): Promise<Cohort> {
    const response = await api.post<Cohort>(`/cohorts/${cohortId}/courses`, { course_id: courseId })
    invalidateCourseLists()
    return response.data
  },

  async detachCourseFromCohort(cohortId: string, courseId: string): Promise<void> {
    await api.delete(`/cohorts/${cohortId}/courses/${courseId}`)
    invalidateCourseLists()
  },

  // ----------------- admin: cohort x students -----------------

  async listCohortStudents(cohortId: string): Promise<CohortStudent[]> {
    const response = await api.get<CohortStudent[]>(`/cohorts/${cohortId}/students`)
    return response.data
  },

  async addCohortStudent(
    cohortId: string,
    body: { user_id?: string; email?: string },
  ): Promise<{ user_id: string; course_ids: string[] }> {
    const response = await api.post<{ user_id: string; course_ids: string[] }>(
      `/cohorts/${cohortId}/students`,
      body,
    )
    return response.data
  },

  async removeCohortStudent(cohortId: string, userId: string): Promise<void> {
    await api.delete(`/cohorts/${cohortId}/students/${userId}`)
  },
}
