import type {
  StudentAssignmentResult,
  StudentChapterInfo,
  StudentProgressEntry,
  StudentQuizResult,
} from "@/types"
import { formatDateLong } from "@/i18n/format"

export type StudentData = StudentProgressEntry
export type QuizResult = StudentQuizResult
export type AssignmentResult = StudentAssignmentResult
export type ChapterInfo = StudentChapterInfo

export type SortColumn = "name" | "progress" | "last_activity"
export type SortDirection = "asc" | "desc"

// quizAvg / assignmentAvg / overallGrade are now computed server-side and
// arrive on the summary row (``quiz_avg`` / ``assignment_avg`` /
// ``overall_grade``) so the board never has to load every student's full
// result arrays. The per-chapter breakdown is fetched lazily on row expand.

export function formatDate(d: string | null): string {
  if (!d) return "—"
  return formatDateLong(d, { month: "short" })
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
