import api from "./api"
import { cacheGet, cacheSet } from "@/lib/cache"
import type { Cohort } from "@/types"

/**
 * Cohort service — read-only here. Write surfaces moved to the
 * admin-only top-level API per ADR-010; the admin UI that consumes
 * them will live in `pages/Admin/cohorts/*` (issue #212).
 *
 * The one method that stays is ``getCourseCohorts`` — used by the
 * catalog's enroll dialog cohort dropdown and (when shipped) the
 * teacher's gradebook cohort filter. Backend now resolves this
 * through the ``cohort_courses`` junction.
 */
export const cohortsService = {
  async getCourseCohorts(courseId: string): Promise<Cohort[]> {
    const key = `cohorts:course:${courseId}`
    const cached = cacheGet<Cohort[]>(key)
    if (cached) return cached
    const response = await api.get<Cohort[]>(`/cohorts/course/${courseId}`)
    cacheSet(key, response.data, 2 * 60 * 1000)
    return response.data
  },
}
