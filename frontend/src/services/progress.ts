import api from "./api"
import { cached, cacheInvalidatePrefix, CACHE_TTL } from "@/lib/cache"
import type {
  CourseGradebookMatrix,
  StudentProgressDetail,
  StudentProgressResponse,
} from "@/types"

export const progressService = {
  /**
   * The student's own statement that they have read a chapter.
   *
   * Explicit rather than inferred from scrolling: a heuristic credits the
   * skimmer who reaches the bottom and misses the careful reader on a phone
   * who closes the tab. One request, and the student decides.
   */
  async markRead(chapterId: string): Promise<void> {
    await api.put(`/progress/chapter/${chapterId}/read`)
    // Their own progress and every teacher-facing roll-up move together, so a
    // student who marks a chapter read does not see one number change and
    // another lag behind for a minute.
    cacheInvalidatePrefix("progress:my:")
    cacheInvalidatePrefix("progress:students:")
    cacheInvalidatePrefix("progress:detail:")
  },

  async teacherMarkComplete(chapterId: string, studentId: string): Promise<void> {
    await api.put(`/progress/chapter/${chapterId}/student/${studentId}/complete`)
    cacheInvalidatePrefix("progress:students:")
    cacheInvalidatePrefix("progress:detail:")
    cacheInvalidatePrefix("progress:gradebook:")
    cacheInvalidatePrefix("analytics:course:")
  },

  async teacherMarkIncomplete(chapterId: string, studentId: string): Promise<void> {
    await api.put(`/progress/chapter/${chapterId}/student/${studentId}/incomplete`)
    cacheInvalidatePrefix("progress:students:")
    cacheInvalidatePrefix("progress:detail:")
    cacheInvalidatePrefix("progress:gradebook:")
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

  async getGradebookMatrix(courseId: string): Promise<CourseGradebookMatrix> {
    // Full students x chapters matrix for the gradebook spreadsheet. Separate
    // from getStudentProgress (the slim progress-board list) because the
    // gradebook needs every student's per-chapter breakdown at once.
    return cached(`progress:gradebook:${courseId}`, CACHE_TTL.THIRTY_SECONDS, async () => {
      const response = await api.get<CourseGradebookMatrix>(
        `/progress/course/${courseId}/gradebook`,
      )
      return response.data
    })
  },

  async getStudentProgressDetail(
    courseId: string,
    studentId: string,
  ): Promise<StudentProgressDetail> {
    // Per-student chapter breakdown, fetched lazily when a progress-board row
    // expands. Cached per (course, student) so re-expanding a row is instant.
    return cached(
      `progress:detail:${courseId}:${studentId}`,
      CACHE_TTL.THIRTY_SECONDS,
      async () => {
        const response = await api.get<StudentProgressDetail>(
          `/progress/course/${courseId}/students/${studentId}/detail`,
        )
        return response.data
      },
    )
  },
}
