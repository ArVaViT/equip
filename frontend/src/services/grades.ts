import api from "./api"
import { cached, cacheInvalidate, cacheInvalidatePrefix, CACHE_TTL } from "@/lib/cache"
import type { GradingConfig, GradeSummaryResponse, StudentGrade } from "@/types"

export const gradesService = {
  async getCourseGrades(courseId: string): Promise<StudentGrade[]> {
    return cached(`grades:course:${courseId}`, CACHE_TTL.ONE_MINUTE, async () => {
      const response = await api.get<StudentGrade[]>(`/grades/course/${courseId}`)
      return response.data
    })
  },

  async upsertGrade(
    courseId: string,
    studentId: string,
    data: { grade?: string; comment?: string },
  ): Promise<StudentGrade> {
    const response = await api.put<StudentGrade>(
      `/grades/course/${courseId}/student/${studentId}`,
      data,
    )
    cacheInvalidate(`grades:course:${courseId}`)
    cacheInvalidate(`grades:summary:${courseId}`)
    cacheInvalidatePrefix("grades:my")
    return response.data
  },

  async getMyGrades(): Promise<StudentGrade[]> {
    return cached("grades:my", CACHE_TTL.ONE_MINUTE, async () => {
      const response = await api.get<StudentGrade[]>("/grades/my")
      return response.data
    })
  },

  async updateGradingConfig(courseId: string, data: GradingConfig): Promise<GradingConfig> {
    const response = await api.put<GradingConfig>(`/grades/course/${courseId}/config`, data)
    cacheInvalidate(`grades:summary:${courseId}`)
    cacheInvalidate(`grades:course:${courseId}`)
    cacheInvalidate(`analytics:course:${courseId}`)
    return response.data
  },

  async getGradeSummary(courseId: string): Promise<GradeSummaryResponse> {
    return cached(`grades:summary:${courseId}`, CACHE_TTL.ONE_MINUTE, async () => {
      const response = await api.get<GradeSummaryResponse>(
        `/grades/course/${courseId}/summary`,
      )
      return response.data
    })
  },

  async exportGradesCSV(courseId: string): Promise<Blob> {
    const response = await api.get(`/grades/course/${courseId}/export-csv`, {
      responseType: "blob",
    })
    return response.data
  },
}
