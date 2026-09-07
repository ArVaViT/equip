/**
 * Shared types for the Gradebook feature. Most of these mirror the
 * shapes returned by the progress and grade-summary endpoints, narrowed
 * to the fields the UI actually consumes.
 */

import type { CourseGroupInfo } from "@/types"

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
  /** The heading this lesson sits under — a module id, or
   *  `UNGROUPED_GROUP_ID` for a lesson the course groups under nothing.
   *  Never null: the report substitutes the sentinel, so a board can group
   *  by this value alone. */
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

/**
 * A heading on the gradebook. Was a module and only a module; now it is
 * whatever the report groups by, which includes the stand-in group for the
 * lessons in no module — `is_ungrouped` is how a screen tells them apart,
 * and the stand-in's `title` is empty because the wording is the screen's to
 * choose. The name stays `ModuleInfo` while its readers migrate.
 */
export type ModuleInfo = CourseGroupInfo

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

