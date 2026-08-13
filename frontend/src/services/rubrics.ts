import api from "./api"
import type { Rubric, RubricCreatePayload, SubmissionRubric } from "@/types"

/**
 * Marking standards (§6.3 of the assessment design).
 *
 * Nothing here sends points. The client sends which level was chosen, and the
 * server reads the number from it — a mark that carries its own number is a
 * number the server has to trust.
 */
export const rubricsService = {
  async listForCourse(courseId: string): Promise<Rubric[]> {
    const response = await api.get<Rubric[]>("/rubrics", { params: { course_id: courseId } })
    return response.data
  },

  async create(payload: RubricCreatePayload): Promise<Rubric> {
    const response = await api.post<Rubric>("/rubrics", payload)
    return response.data
  },

  /** Attach to an assignment. The rubric's total becomes the assignment's maximum. */
  async attach(assignmentId: string, rubricId: string): Promise<Rubric> {
    const response = await api.post<Rubric>(`/rubrics/attach/${assignmentId}`, undefined, {
      params: { rubric_id: rubricId },
    })
    return response.data
  },

  /** The grid and what was chosen on it. Readable by the teacher and by the author. */
  async forSubmission(submissionId: string): Promise<SubmissionRubric> {
    const response = await api.get<SubmissionRubric>(`/rubrics/submission/${submissionId}`)
    return response.data
  },

  /**
   * Record the levels chosen. The work is graded only once every criterion has
   * one — a half-filled grid published as a mark says 40% when the third
   * criterion has simply not been reached.
   */
  async setMarks(
    submissionId: string,
    marks: { criterion_id: string; level_id: string; comment?: string }[],
    feedback?: string,
  ): Promise<SubmissionRubric> {
    const response = await api.put<SubmissionRubric>(`/rubrics/submission/${submissionId}/marks`, {
      marks,
      feedback,
    })
    return response.data
  },
}
