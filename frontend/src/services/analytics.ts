import api from "./api"
import { cached, CACHE_TTL } from "@/lib/cache"

interface CourseAnalyticsEnrollment {
  enrollment_id: string
  user_id: string
  full_name: string | null
  email: string
  progress: number
  enrolled_at: string | null
}

interface CourseAnalytics {
  course_id: string
  course_title: string
  total_students: number
  avg_progress: number
  completion_count: number
  enrollments: CourseAnalyticsEnrollment[]
}

/** A student slipping away in one of the caller's courses (`GET /analytics/at-risk`). */
export interface StudentAtRisk {
  student_id: string
  full_name: string
  /** The address the gradebook shows, for the card's "write" button. */
  email?: string | null
  course_id: string
  course_title: string | null
  last_activity: string
  quiet_days: number
  missed_deadlines: number
}

export const analyticsService = {
  /** Quiet for a week, or two deadlines missed — in the caller's own courses. */
  async getStudentsAtRisk(): Promise<StudentAtRisk[]> {
    return cached("analytics:at-risk", CACHE_TTL.THIRTY_SECONDS, async () => {
      const response = await api.get<StudentAtRisk[]>("/analytics/at-risk")
      return response.data
    })
  },

  async getCourseAnalyticsAPI(courseId: string): Promise<CourseAnalytics> {
    return cached(`analytics:course:${courseId}`, CACHE_TTL.THIRTY_SECONDS, async () => {
      const response = await api.get<CourseAnalytics>(`/analytics/course/${courseId}`)
      return response.data
    })
  },
}
