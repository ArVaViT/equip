import type {
  StudentAssignmentResult,
  StudentChapterInfo,
  StudentProgressEntry,
  StudentQuizResult,
} from "@/types"
import { formatDate as formatDateI18n } from "@/i18n/format"

export type StudentData = StudentProgressEntry
export type QuizResult = StudentQuizResult
export type AssignmentResult = StudentAssignmentResult
export type ChapterInfo = StudentChapterInfo

export type SortColumn = "name" | "progress" | "last_activity"
export type SortDirection = "asc" | "desc"

/** Average quiz percentage, or null if the student has no quiz attempts. */
export function quizAvg(student: StudentData): number | null {
  if (student.quiz_results.length === 0) return null
  const total = student.quiz_results.reduce(
    (sum, q) => sum + (q.score / q.max_score) * 100,
    0,
  )
  return Math.round(total / student.quiz_results.length)
}

/** Average graded-assignment percentage, or null if nothing has been graded. */
export function assignmentAvg(student: StudentData): number | null {
  const graded = student.assignment_results.filter((a) => a.grade !== null)
  if (graded.length === 0) return null
  const total = graded.reduce((sum, a) => sum + (a.grade! / a.max_score) * 100, 0)
  return Math.round(total / graded.length)
}

/**
 * Simple mean of quizAvg and assignmentAvg. We intentionally do NOT weight
 * by attempt count — a single low quiz shouldn't skew the grade more than
 * graded assignments would.
 */
export function overallGrade(student: StudentData): number | null {
  const scores: number[] = []
  const qAvg = quizAvg(student)
  const aAvg = assignmentAvg(student)
  if (qAvg !== null) scores.push(qAvg)
  if (aAvg !== null) scores.push(aAvg)
  if (scores.length === 0) return null
  return Math.round(scores.reduce((a, b) => a + b, 0) / scores.length)
}

export function formatDate(d: string | null): string {
  if (!d) return "—"
  return formatDateI18n(d, {
    month: "short",
    day: "numeric",
    year: "numeric",
  })
}

/** Translator type matches react-i18next's ``useTranslation().t``. */
type Translator = (key: string, options?: { count?: number }) => string

/** "3m ago" / "5d ago" / falls back to formatDate after 7 days.
 *
 * Takes the translator as a parameter so this stays a pure function —
 * the caller passes ``t`` from ``useTranslation()``. The i18next plural
 * machinery handles the per-locale ``minutesAgo_one`` / ``_few`` /
 * ``_many`` forms via the ``count`` option.
 */
export function relativeTime(d: string | null, t: Translator): string {
  if (!d) return t("studentProgress.relative.never")
  const diff = Date.now() - new Date(d).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 60) return t("studentProgress.relative.minutesAgo", { count: mins })
  const hours = Math.floor(mins / 60)
  if (hours < 24) return t("studentProgress.relative.hoursAgo", { count: hours })
  const days = Math.floor(hours / 24)
  if (days < 7) return t("studentProgress.relative.daysAgo", { count: days })
  return formatDate(d)
}

export function averageProgress(students: StudentData[]): number {
  if (students.length === 0) return 0
  return Math.round(students.reduce((sum, s) => sum + s.progress, 0) / students.length)
}

export function completionRate(students: StudentData[]): number {
  if (students.length === 0) return 0
  const completed = students.filter((s) => s.progress >= 100).length
  return Math.round((completed / students.length) * 100)
}
