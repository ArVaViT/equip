import api from "./api"
import { cached, cacheInvalidate, cacheInvalidatePrefix, CACHE_TTL } from "@/lib/cache"
import type { CourseReview } from "@/types"

export const reviewsService = {
  async getCourseReviews(courseId: string): Promise<CourseReview[]> {
    return cached(`reviews:course:${courseId}`, CACHE_TTL.TWO_MINUTES, async () => {
      const response = await api.get<CourseReview[]>(`/reviews/course/${courseId}`)
      return response.data
    })
  },

  async submitReview(
    courseId: string,
    data: { rating: number; comment?: string },
  ): Promise<CourseReview> {
    const response = await api.post<CourseReview>(`/reviews/course/${courseId}`, data)
    cacheInvalidate(`reviews:course:${courseId}`)
    return response.data
  },

  async deleteReview(id: string): Promise<void> {
    await api.delete(`/reviews/${id}`)
    cacheInvalidatePrefix("reviews:course:")
  },
}
