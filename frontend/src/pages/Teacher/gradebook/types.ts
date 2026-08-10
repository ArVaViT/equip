/**
 * Shared types for the Gradebook feature. Most of these mirror the
 * shapes returned by the progress and grade-summary endpoints, narrowed
 * to the fields the UI actually consumes.
 */

export const SORT_FIELDS = [
  "name",
  "quiz",
  "assignment",
  "final",
  "letter",
] as const
export type SortField = (typeof SORT_FIELDS)[number]
export type SortDir = "asc" | "desc"

export const TABS = ["summary", "table"] as const
export type ActiveTab = (typeof TABS)[number]

export interface ChapterInfo {
  id: string
  title: string
  module_id: string
  chapter_type: string
  completed: boolean
  completed_by: "self" | "teacher" | "quiz" | "excused" | null
  /** `awaiting_grading` — submitted, but its open answers are still unread, so
   *  `score` is a running total and not a result. */
  quiz_result: {
    score: number
    max_score: number
    passed: boolean
    awaiting_grading?: boolean
  } | null
  assignment_result: {
    status: string
    grade: number | null
    max_score?: number
  } | null
}

export interface StudentProgressData {
  id: string
  full_name: string
  email: string
  progress: number
  chapters_completed: number
  total_chapters: number
  chapters: ChapterInfo[]
}

export interface ModuleInfo {
  id: string
  title: string
  order_index: number
}

export interface ProgressResponse {
  course_id: string
  course_title: string
  total_chapters: number
  total_students: number
  modules: ModuleInfo[]
  students: StudentProgressData[]
}

export interface GradeForm {
  grade: string
  comment: string
}

