import api from "./api"

export type ReadinessSeverity = "critical" | "recommended" | "polish"

export type ReadinessSubjectType =
  | "course"
  | "module"
  | "chapter"
  | "quiz"
  | "assignment"

export type ReadinessActionType =
  | "set_description"
  | "set_cover_image"
  | "open_enrollment"
  | "add_module"
  | "open_module"
  | "open_chapter"
  | "open_quiz"
  | "open_assignment"
  | "open_grading_weights"

export interface ReadinessSubject {
  type: ReadinessSubjectType
  id: string
  title: string
}

export interface ReadinessAction {
  type: ReadinessActionType
  params: Record<string, string>
}

export interface ReadinessCheck {
  id: string
  severity: ReadinessSeverity
  passed: boolean
  message_key: string
  subject?: ReadinessSubject | null
  action?: ReadinessAction | null
}

export interface ReadinessReport {
  course_id: string
  total: number
  passing: number
  critical_failing: number
  score: number
  checks: ReadinessCheck[]
}

/**
 * Readiness checklist for the course editor. Backend computes and we
 * just render — keeps the truth in one place.
 */
export const courseReadinessService = {
  async get(courseId: string): Promise<ReadinessReport> {
    const { data } = await api.get<ReadinessReport>(
      `/courses/${courseId}/readiness`,
    )
    return data
  },
}
