import api from "./api"
import { cached, cacheInvalidatePrefix, CACHE_TTL } from "@/lib/cache"
import type { StudentProgressResponse } from "@/types"

export const progressService = {
  async teacherMarkComplete(chapterId: string, studentId: string): Promise<void> {
    await api.put(`/progress/chapter/${chapterId}/student/${studentId}/complete`)
    cacheInvalidatePrefix("progress:students:")
    cacheInvalidatePrefix("analytics:course:")
  },

  async teacherMarkIncomplete(chapterId: string, studentId: string): Promise<void> {
    await api.put(`/progress/chapter/${chapterId}/student/${studentId}/incomplete`)
    cacheInvalidatePrefix("progress:students:")
    cacheInvalidatePrefix("analytics:course:")
  },

  async getMyChapterProgress(courseId: string): Promise<string[]> {
    return cached(`progress:my:${courseId}`, CACHE_TTL.ONE_MINUTE, async () => {
      const response = await api.get<string[]>(`/progress/course/${courseId}/my-progress`)
      return response.data
    })
  },

  async getStudentProgress(courseId: string): Promise<StudentProgressResponse> {
    return cached(`progress:students:${courseId}`, CACHE_TTL.THIRTY_SECONDS, async () => {
      const response = await api.get<StudentProgressResponse>(
        `/progress/course/${courseId}/students`,
      )
      return response.data
    })
  },
}
