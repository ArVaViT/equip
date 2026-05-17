import { useMemo, useState } from "react"
import { Link } from "react-router-dom"
import { useTranslation } from "react-i18next"
import { Button } from "@/components/ui/button"
import { toast } from "@/lib/toast"
import { coursesService } from "@/services/courses"
import {
  BookOpen,
  ChevronDown,
  ChevronRight,
  ClipboardList,
  FileText,
} from "lucide-react"
import { ChapterBreakdownRow } from "./ChapterBreakdownRow"
import { ProgressBar, ScoreBadge } from "./ProgressBar"
import {
  formatDate,
  relativeTime,
  type AssignmentResult,
  type ChapterInfo,
  type QuizResult,
  type StudentData,
} from "./helpers"

interface Props {
  student: StudentData
  isExpanded: boolean
  onToggle: () => void
  quizAvg: number | null
  assignmentAvg: number | null
  overallGrade: number | null
  courseId: string
  onChapterUpdate: (
    studentId: string,
    chapterId: string,
    completed: boolean,
    completedBy: "teacher" | "self" | null,
  ) => void
}

type ChapterEntry = {
  quiz?: QuizResult
  assignment?: AssignmentResult
  chapterInfo?: ChapterInfo
}

/**
 * Two-row component: the always-visible student summary row, plus the
 * detail row that appears when expanded (per-chapter breakdown, quick
 * actions). Uses render-time memo for the merged chapter map so we don't
 * rebuild it on every keystroke in the outer search input.
 */
export function StudentRow({
  student,
  isExpanded,
  onToggle,
  quizAvg,
  assignmentAvg,
  overallGrade,
  courseId,
  onChapterUpdate,
}: Props) {
  const { t } = useTranslation()
  const [togglingChapter, setTogglingChapter] = useState<string | null>(null)
  const [grantingQuiz, setGrantingQuiz] = useState<string | null>(null)

  const allChapters = useMemo(() => {
    const map = new Map<string, ChapterEntry>()
    for (const ch of student.chapters ?? []) {
      map.set(ch.id, { ...(map.get(ch.id) ?? {}), chapterInfo: ch })
    }
    for (const q of student.quiz_results) {
      map.set(q.chapter_id, { ...(map.get(q.chapter_id) ?? {}), quiz: q })
    }
    for (const a of student.assignment_results) {
      map.set(a.chapter_id, { ...(map.get(a.chapter_id) ?? {}), assignment: a })
    }
    return map
  }, [student.chapters, student.quiz_results, student.assignment_results])

  const handleToggleComplete = async (chapterInfo: ChapterInfo) => {
    setTogglingChapter(chapterInfo.id)
    try {
      if (chapterInfo.completed) {
        await coursesService.teacherMarkIncomplete(chapterInfo.id, student.id)
        onChapterUpdate(student.id, chapterInfo.id, false, null)
        toast({ title: t("studentProgress.row.markedIncomplete"), variant: "success" })
      } else {
        await coursesService.teacherMarkComplete(chapterInfo.id, student.id)
        onChapterUpdate(student.id, chapterInfo.id, true, "teacher")
        toast({ title: t("studentProgress.row.markedComplete"), variant: "success" })
      }
    } catch {
      toast({ title: t("studentProgress.row.toggleFailed"), variant: "destructive" })
    } finally {
      setTogglingChapter(null)
    }
  }

  const handleGrantExtraAttempt = async (quizId: string) => {
    setGrantingQuiz(quizId)
    try {
      await coursesService.grantExtraAttempts(quizId, student.id, 1)
      toast({ title: t("studentProgress.row.extraAttemptGranted"), variant: "success" })
    } catch {
      toast({ title: t("studentProgress.row.extraAttemptFailed"), variant: "destructive" })
    } finally {
      setGrantingQuiz(null)
    }
  }

  return (
    <>
      <tr
        className="border-b last:border-0 cursor-pointer hover:bg-muted/50 transition-colors"
        onClick={onToggle}
      >
        <td className="py-3 pr-2">
          {isExpanded ? (
            <ChevronDown className="h-4 w-4 text-muted-foreground" strokeWidth={1.75} />
          ) : (
            <ChevronRight className="h-4 w-4 text-muted-foreground" strokeWidth={1.75} />
          )}
        </td>
        <td className="py-3 font-medium">{student.full_name}</td>
        <td className="py-3 text-muted-foreground">{student.email}</td>
        <td className="py-3">
          <ProgressBar value={student.progress} />
        </td>
        <td className="py-3 text-center tabular-nums">
          {student.chapters_completed}/{student.total_chapters}
        </td>
        <td className="py-3">
          <ScoreBadge value={quizAvg} />
        </td>
        <td className="py-3">
          <ScoreBadge value={assignmentAvg} />
        </td>
        <td className="py-3 text-muted-foreground text-xs">
          {relativeTime(student.last_activity, t)}
        </td>
      </tr>
      {isExpanded && (
        <tr>
          <td colSpan={8} className="p-0">
            <div className="bg-muted/30 border-y px-6 py-5 space-y-5">
              <div className="flex flex-wrap gap-6">
                <SummaryStat label={t("studentProgress.row.overallGrade")}>
                  <p className="text-xl font-bold">
                    {overallGrade !== null
                      ? `${overallGrade}%`
                      : t("studentProgress.row.overallGradeNa")}
                  </p>
                </SummaryStat>
                <SummaryStat label={t("studentProgress.row.enrolled")}>
                  <p className="text-sm font-medium">{formatDate(student.enrolled_at)}</p>
                </SummaryStat>
                <SummaryStat label={t("studentProgress.row.chaptersCompleted")}>
                  <p className="text-sm font-medium">
                    {t("studentProgress.row.chaptersCompletedValue", {
                      done: student.chapters_completed,
                      total: student.total_chapters,
                    })}
                  </p>
                </SummaryStat>
                <SummaryStat label={t("studentProgress.row.progress")}>
                  <ProgressBar value={student.progress} />
                </SummaryStat>
              </div>

              {allChapters.size > 0 && (
                <div>
                  <h4 className="text-sm font-semibold mb-3 flex items-center gap-1.5">
                    <BookOpen className="h-4 w-4" strokeWidth={1.75} />
                    {t("studentProgress.row.chapterBreakdown")}
                  </h4>
                  <div className="space-y-2">
                    {Array.from(allChapters.entries()).map(([id, entry]) => (
                      <ChapterBreakdownRow
                        key={id}
                        chapterId={id}
                        chapterInfo={entry.chapterInfo}
                        quiz={entry.quiz}
                        assignment={entry.assignment}
                        togglingChapterId={togglingChapter}
                        grantingQuizId={grantingQuiz}
                        onToggleComplete={handleToggleComplete}
                        onGrantExtraAttempt={handleGrantExtraAttempt}
                      />
                    ))}
                  </div>
                </div>
              )}

              <div className="flex items-center gap-2 pt-1">
                <Link to={`/teacher/courses/${courseId}/gradebook`}>
                  <Button size="sm" variant="outline">
                    <ClipboardList className="h-3.5 w-3.5 mr-1.5" strokeWidth={1.75} />
                    {t("studentProgress.row.gradebookButton")}
                  </Button>
                </Link>
                <Link to={`/teacher/courses/${courseId}/analytics`}>
                  <Button size="sm" variant="ghost">
                    <FileText className="h-3.5 w-3.5 mr-1.5" strokeWidth={1.75} />
                    {t("studentProgress.row.viewAnalytics")}
                  </Button>
                </Link>
              </div>
            </div>
          </td>
        </tr>
      )}
    </>
  )
}

function SummaryStat({
  label,
  children,
}: {
  label: string
  children: React.ReactNode
}) {
  return (
    <div>
      <p className="text-xs text-muted-foreground mb-1">{label}</p>
      {children}
    </div>
  )
}
