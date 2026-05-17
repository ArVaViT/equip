import api from "./api"
import { cached, cacheInvalidate, cacheInvalidatePrefix, CACHE_TTL } from "@/lib/cache"
import type { Enrollment } from "@/types"

export const enrollmentsService = {
  async enrollInCourse(courseId: string, cohortId?: string): Promise<Enrollment> {
    const response = await api.post<Enrollment>(
      `/courses/${courseId}/enroll`,
      cohortId ? { cohort_id: cohortId } : {},
    )
    cacheInvalidate("courses:my")
    cacheInvalidate(`courses:enrollment-status:${courseId}`)
    cacheInvalidatePrefix("calendar:events:")
    cacheInvalidatePrefix("progress:my:")
    return response.data
  },

  async getMyCourses(): Promise<Enrollment[]> {
    // HomePage, ProfilePage, CalendarPage, and CertificatesPage all call this
    // on mount. Without the short TTL we'd issue four identical requests for
    // /users/me/courses during a routine navigation.
    return cached("courses:my", CACHE_TTL.ONE_MINUTE, async () => {
      const response = await api.get<Enrollment[]>("/users/me/courses")
      return response.data
    })
  },

  async getEnrollmentStatus(
    courseId: string,
  ): Promise<{ enrolled: boolean; enrollment: Enrollment | null }> {
    return cached(`courses:enrollment-status:${courseId}`, CACHE_TTL.ONE_MINUTE, async () => {
      const response = await api.get<{ enrolled: boolean; enrollment: Enrollment | null }>(
        `/courses/${courseId}/enrollment-status`,
      )
      return response.data
    })
  },
}
