import api from "./api"
import { cacheInvalidatePrefix } from "@/lib/cache"
import type { Assignment, AssignmentSubmission } from "@/types"

type AssignmentCreateData = {
  chapter_id: string
  title: string
  description?: string | null
  max_score?: number
  due_date?: string | null
}

export const assignmentsService = {
  async getChapterAssignments(chapterId: string): Promise<Assignment[]> {
    const response = await api.get<Assignment[]>(`/assignments/chapter/${chapterId}`)
    return response.data
  },

  /**
   * Editor-only fetch: forces source-language `title` / `description`
   * columns regardless of the viewer's `preferred_locale`. Use from
   * `AssignmentEditor` so a teacher in EN UI editing their RU assignment
   * doesn't see the EN translation in the editable fields (a PATCH would
   * then overwrite the source `title` column).
   *
   * Owner / admin only — the backend returns 403 for anyone else.
   */
  async getChapterAssignmentsForEdit(chapterId: string): Promise<Assignment[]> {
    const response = await api.get<Assignment[]>(
      `/assignments/chapter/${chapterId}`,
      { params: { source: 1 } },
    )
    return response.data
  },

  async createAssignment(data: AssignmentCreateData): Promise<Assignment> {
    const response = await api.post<Assignment>("/assignments", data)
    return response.data
  },

  async updateAssignment(
    id: string,
    data: Partial<AssignmentCreateData>,
  ): Promise<Assignment> {
    const response = await api.put<Assignment>(`/assignments/${id}`, data)
    return response.data
  },

  async deleteAssignment(id: string): Promise<void> {
    await api.delete(`/assignments/${id}`)
  },

  async submitAssignment(
    id: string,
    data: { content?: string; file_url?: string },
  ): Promise<AssignmentSubmission> {
    const response = await api.post<AssignmentSubmission>(`/assignments/${id}/submit`, data)
    cacheInvalidatePrefix("progress:my:")
    return response.data
  },

  async getSubmissions(assignmentId: string): Promise<AssignmentSubmission[]> {
    const response = await api.get<AssignmentSubmission[]>(
      `/assignments/${assignmentId}/submissions`,
    )
    return response.data
  },

  async getMySubmissions(assignmentId: string): Promise<AssignmentSubmission[]> {
    const response = await api.get<AssignmentSubmission[]>(
      `/assignments/${assignmentId}/my-submissions`,
    )
    return response.data
  },

  async gradeSubmission(
    submissionId: string,
    data: { grade: number; feedback?: string; status: string },
  ): Promise<AssignmentSubmission> {
    const response = await api.put<AssignmentSubmission>(
      `/assignments/submissions/${submissionId}/grade`,
      data,
    )
    cacheInvalidatePrefix("grades:course:")
    cacheInvalidatePrefix("grades:summary:")
    cacheInvalidatePrefix("grades:my")
    cacheInvalidatePrefix("analytics:course:")
    cacheInvalidatePrefix("progress:students:")
    return response.data
  },
}
