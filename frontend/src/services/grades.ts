import api from "./api"
import { cached, cacheInvalidate, cacheInvalidatePrefix, CACHE_TTL } from "@/lib/cache"
import type {
  GradeExemption,
  GradeSheet,
  MyCourseGrade,
  GradingConfig,
  GradeSummaryResponse,
  StudentGrade,
} from "@/types"

/** An exemption moves a grade *and* a completion, so both sides go stale. */
function invalidateAfterExemption(courseId: string): void {
  cacheInvalidate(`grades:course:${courseId}`)
  cacheInvalidate(`grades:summary:${courseId}`)
  cacheInvalidatePrefix("grades:my")
  cacheInvalidatePrefix("progress:students:")
  cacheInvalidatePrefix("progress:detail:")
  cacheInvalidatePrefix("progress:gradebook:")
  cacheInvalidatePrefix("analytics:course:")
}

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
    data: { override_code?: string; override_score?: number; reason?: string; comment?: string },
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

  /**
   * Remove a hand-set grade so the computed one takes over again.
   *
   * There was no way to do this before: the write path read an omitted field
   * as "leave it alone", so a mistaken F was permanent.
   */
  async clearGrade(courseId: string, studentId: string): Promise<void> {
    await api.delete(`/grades/course/${courseId}/student/${studentId}`)
    cacheInvalidate(`grades:course:${courseId}`)
    cacheInvalidate(`grades:summary:${courseId}`)
    cacheInvalidatePrefix("grades:my")
  },

  /**
   * Excuse a student from one piece of work — hospital, a funeral, joining
   * three weeks late. It leaves both denominators: the item stops counting
   * toward the grade AND its chapter counts as done, so progress can still
   * reach 100 and the certificate is not blocked forever.
   *
   * Every progress cache is invalidated because the second half of that is a
   * completion change, not just a grade change.
   */
  async excuseStudent(
    courseId: string,
    studentId: string,
    data: { item_type: "quiz" | "assignment"; item_id: string; reason?: string },
  ): Promise<GradeExemption> {
    const response = await api.post<GradeExemption>(
      `/grades/course/${courseId}/student/${studentId}/exemptions`,
      data,
    )
    invalidateAfterExemption(courseId)
    return response.data
  },

  /** Take an exemption back: the work counts again and its chapter reopens. */
  async removeExemption(
    courseId: string,
    studentId: string,
    itemType: "quiz" | "assignment",
    itemId: string,
  ): Promise<void> {
    await api.delete(
      `/grades/course/${courseId}/student/${studentId}/exemptions/${itemType}/${itemId}`,
    )
    invalidateAfterExemption(courseId)
  },

  async listExemptions(courseId: string, studentId: string): Promise<GradeExemption[]> {
    const response = await api.get<GradeExemption[]>(
      `/grades/course/${courseId}/student/${studentId}/exemptions`,
    )
    return response.data
  },

  /**
   * The student's own standing in one course — both grades, the per-item list
   * and the teacher's comment. Self-only on the server: there is no student
   * parameter to pass, which is the point.
   */
  async getMyCourseGrade(courseId: string): Promise<MyCourseGrade> {
    // Keyed under `grades:my` deliberately: every teacher write in this file
    // already invalidates that prefix, so a hand-set grade reaches the student
    // by the same path as everything else. `grades:mine:` would have been
    // caught by the same prefix purely by accident of spelling.
    return cached(`grades:my:course:${courseId}`, CACHE_TTL.ONE_MINUTE, async () => {
      const response = await api.get<MyCourseGrade>(`/grades/my/${courseId}/breakdown`)
      return response.data
    })
  },

  /** The ведомость standing for this поток, or `null` if none is closed. */
  async getGradeSheet(courseId: string, cohortId?: string | null): Promise<GradeSheet | null> {
    const response = await api.get<GradeSheet | null>(`/grades/course/${courseId}/sheet`, {
      params: cohortId ? { cohort_id: cohortId } : undefined,
    })
    return response.data
  },

  /** Close it — freezes every student's result. Director-only on the server. */
  async closeGradeSheet(courseId: string, cohortId?: string | null): Promise<GradeSheet> {
    const response = await api.post<GradeSheet>(
      `/grades/course/${courseId}/sheet`,
      undefined,
      { params: cohortId ? { cohort_id: cohortId } : undefined },
    )
    return response.data
  },

  async reopenGradeSheet(sheetId: string, reason: string): Promise<GradeSheet> {
    const response = await api.post<GradeSheet>(`/grades/sheet/${sheetId}/reopen`, { reason })
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
