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

export const analyticsService = {
  async getCourseAnalyticsAPI(courseId: string): Promise<CourseAnalytics> {
    return cached(`analytics:course:${courseId}`, CACHE_TTL.THIRTY_SECONDS, async () => {
      const response = await api.get<CourseAnalytics>(`/analytics/course/${courseId}`)
      return response.data
    })
  },
}
