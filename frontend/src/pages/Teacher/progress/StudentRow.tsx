import { useEffect, useMemo, useState } from "react"
import { Link } from "react-router-dom"
import { useTranslation } from "react-i18next"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { Modal } from "@/components/patterns"
import { toast } from "@/lib/toast"
import { cn } from "@/lib/utils"
import { coursesService } from "@/services/courses"
import { gradesService } from "@/services/grades"
import type { RetakeRequest, StudentProgressDetail } from "@/types"
import {
  BookOpen,
  ChevronDown,
  ChevronRight,
  ClipboardList,
  FileText,
  HandHelping,
  Loader2,
} from "lucide-react"
import { ChapterBreakdownRow } from "./ChapterBreakdownRow"
import { GradeHistory } from "./GradeHistory"
import { officialGrade } from "./officialGrade"
import { ProgressBar, ScoreBadge } from "./ProgressBar"
import {
  formatDate,
  relativeTime,
  type AssignmentResult,
  type ChapterInfo,
  type QuizResult,
  type StudentData,
} from "./helpers"

/**
 * Blocker codes this build has words for. A code from a newer backend renders
 * as nothing rather than as a raw key — the marker still says a student asked,
 * and the work is listed below either way.
 */
const NAMED_BLOCKERS = new Set([
  "course_not_complete",
  "work_not_graded",
  "work_returned",
  "work_not_submitted",
  "quizzes_not_passed",
  "below_threshold",
  "not_assessed",
])

function namedBlockers(codes: string[]): string[] {
  return codes.filter((code) => NAMED_BLOCKERS.has(code))
}

interface Props {
  student: StudentData
  /** Their open «запросить пересдачу», if they have one (D12). */
  retakeRequest?: RetakeRequest
  isExpanded: boolean
  onToggle: () => void
  quizAvg: number | null
  assignmentAvg: number | null
  courseId: string
  onChapterUpdate: (
    studentId: string,
    chapterId: string,
    completed: boolean,
    completedBy: "teacher" | "self" | "excused" | null,
  ) => void
  /** A row of the desktop table, or an item of the phone list. */
  layout?: "table" | "list"
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
  retakeRequest,
  isExpanded,
  onToggle,
  quizAvg,
  assignmentAvg,
  courseId,
  onChapterUpdate,
  layout = "table",
}: Props) {
  const { t } = useTranslation()
  const official = officialGrade(student)
  const [togglingChapter, setTogglingChapter] = useState<string | null>(null)
  const [grantingQuiz, setGrantingQuiz] = useState<string | null>(null)
  const [excusingChapter, setExcusingChapter] = useState<string | null>(null)
  // The chapter awaiting a reason. Waiving work is a decision someone will be
  // asked about later, so the reason is worth one dialog.
  const [excuseTarget, setExcuseTarget] = useState<ChapterInfo | null>(null)
  const [excuseReason, setExcuseReason] = useState("")
  // The per-chapter breakdown is fetched lazily the first time a row expands —
  // the list payload only carries summary scalars, so each student's full
  // chapter/quiz/assignment detail is pulled on demand here.
  const [detail, setDetail] = useState<StudentProgressDetail | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [detailError, setDetailError] = useState(false)

  useEffect(() => {
    if (!isExpanded || detail || detailError) return
    // ``detailLoading`` is not a dependency. It was, and setting it below
    // re-ran this effect, whose cleanup cancelled the request it had just
    // sent: the breakdown said "Loading…" for ever. A teacher tapped his
    // first student three times on 2026-10-15 and gave up.
    let cancelled = false
    setDetailLoading(true)
    coursesService
      .getStudentProgressDetail(courseId, student.id)
      .then((d) => {
        if (!cancelled) setDetail(d)
      })
      .catch(() => {
        if (!cancelled) setDetailError(true)
      })
      .finally(() => {
        if (!cancelled) setDetailLoading(false)
      })
    return () => {
      cancelled = true
      // Collapsed mid-load: the next expand starts a fresh request.
      setDetailLoading(false)
    }
  }, [isExpanded, detail, detailError, courseId, student.id])

  const allChapters = useMemo(() => {
    const map = new Map<string, ChapterEntry>()
    if (!detail) return map
    for (const ch of detail.chapters) {
      map.set(ch.id, { ...(map.get(ch.id) ?? {}), chapterInfo: ch })
    }
    for (const q of detail.quiz_results) {
      map.set(q.chapter_id, { ...(map.get(q.chapter_id) ?? {}), quiz: q })
    }
    for (const a of detail.assignment_results) {
      map.set(a.chapter_id, { ...(map.get(a.chapter_id) ?? {}), assignment: a })
    }
    return map
  }, [detail])

  const handleToggleComplete = async (chapterInfo: ChapterInfo) => {
    setTogglingChapter(chapterInfo.id)
    const nowCompleted = !chapterInfo.completed
    try {
      if (chapterInfo.completed) {
        await coursesService.teacherMarkIncomplete(chapterInfo.id, student.id)
        toast({ title: t("studentProgress.row.markedIncomplete"), variant: "success" })
      } else {
        await coursesService.teacherMarkComplete(chapterInfo.id, student.id)
        toast({ title: t("studentProgress.row.markedComplete"), variant: "success" })
      }
      // Update the locally-held detail so the expanded breakdown reflects the
      // flip immediately, and bump the parent summary row's progress counts.
      setDetail((prev) =>
        prev
          ? {
              ...prev,
              chapters: prev.chapters.map((ch) =>
                ch.id === chapterInfo.id ? { ...ch, completed: nowCompleted } : ch,
              ),
            }
          : prev,
      )
      onChapterUpdate(student.id, chapterInfo.id, nowCompleted, nowCompleted ? "teacher" : null)
    } catch {
      toast({ title: t("studentProgress.row.toggleFailed"), variant: "destructive" })
    } finally {
      setTogglingChapter(null)
    }
  }

  /** Write the exemption, then mirror both of its halves into the open row. */
  const submitExcuse = async () => {
    const chapter = excuseTarget
    if (!chapter?.gradable_item) return
    setExcusingChapter(chapter.id)
    try {
      await gradesService.excuseStudent(courseId, student.id, {
        item_type: chapter.gradable_item.type,
        item_id: chapter.gradable_item.id,
        reason: excuseReason.trim() || undefined,
      })
      // A chapter the student had already finished keeps the completion it
      // earned — the server leaves it alone, so mirroring "excused" here would
      // put a label on screen that isn't in the database.
      const wasCompleted = chapter.completed
      setDetail((prev) =>
        prev
          ? {
              ...prev,
              chapters: prev.chapters.map((ch) =>
                ch.id === chapter.id && !wasCompleted
                  ? { ...ch, completed: true, completed_by: "excused" }
                  : ch,
              ),
            }
          : prev,
      )
      // The chapter counts as done now, so the summary row's counters move too
      // — that is the half of an exemption teachers don't expect and the half
      // that decides whether a certificate is reachable. Only when it actually
      // changed, or the count drifts up by one for nothing.
      if (!wasCompleted) onChapterUpdate(student.id, chapter.id, true, "excused")
      toast({ title: t("studentProgress.row.excused"), variant: "success" })
      setExcuseTarget(null)
      setExcuseReason("")
    } catch {
      toast({ title: t("studentProgress.row.excuseFailed"), variant: "destructive" })
    } finally {
      setExcusingChapter(null)
    }
  }

  const handleUnexcuse = async (chapter: ChapterInfo) => {
    if (!chapter.gradable_item) return
    setExcusingChapter(chapter.id)
    try {
      await gradesService.removeExemption(
        courseId,
        student.id,
        chapter.gradable_item.type,
        chapter.gradable_item.id,
      )
      setDetail((prev) =>
        prev
          ? {
              ...prev,
              chapters: prev.chapters.map((ch) =>
                ch.id === chapter.id ? { ...ch, completed: false, completed_by: null } : ch,
              ),
            }
          : prev,
      )
      onChapterUpdate(student.id, chapter.id, false, null)
      toast({ title: t("studentProgress.row.exemptionRemoved"), variant: "success" })
    } catch {
      toast({ title: t("studentProgress.row.exemptionRemoveFailed"), variant: "destructive" })
    } finally {
      setExcusingChapter(null)
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

  const list = layout === "list"

  const details = (
    <div className={cn("space-y-5 bg-muted/30", list ? "border-t px-4 py-4" : "border-y px-6 py-5")}>
      {retakeRequest && (
        <div className="rounded-lg border border-warning/40 bg-warning/5 px-3 py-2.5 text-sm">
          <p className="font-medium">{t("studentProgress.retake.title")}</p>
          <p className="mt-0.5 text-ink-muted">
            {/* What stopped them when they asked, so the teacher knows
                which of the four powers below this calls for instead of
                opening four screens to find out. */}
            {namedBlockers(retakeRequest.blockers)
              .map((code) => t(`studentProgress.retake.blocker.${code}`))
              .join(" · ") || t("studentProgress.retake.noDetail")}
          </p>
        </div>
      )}
      <div className={list ? "grid grid-cols-2 gap-x-6 gap-y-4" : "flex flex-wrap gap-6"}>
        {/* The columns a phone's row does not show, said here instead. */}
        {list && (
          <>
            <SummaryStat label={t("studentProgress.table.email")} className="col-span-2">
              <p className="break-all text-sm font-medium">{student.email}</p>
            </SummaryStat>
            <SummaryStat label={t("studentProgress.table.quizAvg")}>
              <ScoreBadge value={quizAvg} />
            </SummaryStat>
            <SummaryStat label={t("studentProgress.table.assignAvg")}>
              <ScoreBadge value={assignmentAvg} />
            </SummaryStat>
            <SummaryStat label={t("studentProgress.table.lastActive")}>
              <p className="text-sm font-medium">{relativeTime(student.last_activity, t)}</p>
            </SummaryStat>
          </>
        )}
        <SummaryStat label={t("studentProgress.row.overallGrade")} className={list ? "col-span-2" : undefined}>
          {/* The official grade, decided the same way the gradebook
              decides it: a teacher's override wins, and an absent
              number says why rather than printing a bare dash. */}
          <p className="text-xl font-bold">
            {official.text ?? t("studentProgress.row.overallGradeNa")}
            {official.isManual && (
              <span className="ml-2 align-middle text-xs font-medium text-info">
                {t("studentProgress.grade.setByTeacher")}
              </span>
            )}
          </p>
          {official.finalText && (
            <p className="text-xs text-ink-muted mt-0.5">
              {t("gradebook.pair.finalShort", { grade: official.finalText })} ·{" "}
              {t("gradebook.pair.explainer")}
            </p>
          )}
          {official.noteKey && (
            <p className="text-xs text-ink-muted mt-0.5">{t(official.noteKey)}</p>
          )}
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
        {/* On a phone the row above already shows it. */}
        {!list && (
          <SummaryStat label={t("studentProgress.row.progress")}>
            <ProgressBar value={student.progress} />
          </SummaryStat>
        )}
      </div>

      <GradeHistory courseId={courseId} studentId={student.id} />

      {detailLoading && (
        <div className="flex items-center gap-2 py-4 text-sm text-ink-muted">
          <Loader2 className="h-4 w-4 animate-spin" strokeWidth={1.75} aria-hidden />
          {t("studentProgress.row.loadingDetail")}
        </div>
      )}
      {detailError && !detailLoading && (
        <div className="flex items-center gap-3 py-4 text-sm text-ink-muted">
          <span>{t("studentProgress.row.detailFailed")}</span>
          <Button
            size="sm"
            variant="outline"
            onClick={() => {
              setDetail(null)
              setDetailError(false)
            }}
          >
            {t("studentProgress.row.retry")}
          </Button>
        </div>
      )}
      {detail && !detailLoading && allChapters.size > 0 && (
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
                excusingChapterId={excusingChapter}
                onToggleComplete={handleToggleComplete}
                onGrantExtraAttempt={handleGrantExtraAttempt}
                onExcuse={(ch) => {
                  setExcuseReason("")
                  setExcuseTarget(ch)
                }}
                onUnexcuse={handleUnexcuse}
              />
            ))}
          </div>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2 pt-1">
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
  )

  const excuseModal = (
    <Modal
      open={excuseTarget !== null}
      onClose={() => setExcuseTarget(null)}
      title={t("studentProgress.excuse.title", { chapter: excuseTarget?.title ?? "" })}
    >
      <div className="space-y-4">
        {/* Said plainly, because the second half surprises people: the work
            stops counting against the grade AND the chapter counts as done,
            which is what keeps the certificate reachable. */}
        <p className="text-sm text-ink-muted">{t("studentProgress.excuse.explainer")}</p>
        <div className="space-y-1.5">
          <Label htmlFor="excuse-reason">{t("studentProgress.excuse.reasonLabel")}</Label>
          <Textarea
            id="excuse-reason"
            rows={3}
            value={excuseReason}
            onChange={(e) => setExcuseReason(e.target.value)}
            placeholder={t("studentProgress.excuse.reasonPlaceholder")}
          />
        </div>
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={() => setExcuseTarget(null)}>
            {t("common.cancel")}
          </Button>
          <Button onClick={submitExcuse} disabled={excusingChapter !== null}>
            {excusingChapter !== null && (
              <Loader2 className="h-4 w-4 mr-1.5 animate-spin" strokeWidth={1.75} aria-hidden />
            )}
            {t("studentProgress.excuse.confirm")}
          </Button>
        </div>
      </div>
    </Modal>
  )

  // A phone gets a list, not a table: the name on one line, the progress, a
  // chevron; everything else in the details a tap opens. The eight-column
  // table was 800px wide there — its headings cut off, the name broken onto
  // two lines beside an address, the open row running off the screen.
  if (list) {
    return (
      <li className="border-b last:border-0">
        <button
          type="button"
          onClick={onToggle}
          aria-expanded={isExpanded}
          className="flex min-h-11 w-full items-center gap-3 py-3 text-left transition-colors hover:bg-muted/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
        >
          <span className="min-w-0 flex-1 truncate font-medium">{student.full_name}</span>
          {retakeRequest && (
            // The student a teacher should open first; the details say why.
            <HandHelping
              className="h-4 w-4 shrink-0 text-warning-ink"
              strokeWidth={1.75}
              role="img"
              aria-label={t("studentProgress.retake.asked")}
            />
          )}
          <ProgressBar value={student.progress} className="w-28 shrink-0" />
          <Chevron open={isExpanded} />
        </button>
        {isExpanded && details}
        {excuseModal}
      </li>
    )
  }

  return (
    <>
      <tr
        className="cursor-pointer border-b transition-colors last:border-0 hover:bg-muted/40"
        onClick={onToggle}
      >
        <td className="py-3 pr-2">
          <Chevron open={isExpanded} />
        </td>
        <td className="py-3 font-medium">
          {student.full_name}
          {retakeRequest && (
            // The row a teacher should open first. A notification is read once
            // and gone; this stays until the request is dealt with, which is
            // the difference between a student being heard and being missed.
            <span className="ml-2 inline-flex items-center gap-1 rounded-md bg-warning/15 px-1.5 py-0.5 align-middle text-xs font-medium text-warning-ink">
              <HandHelping className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
              {t("studentProgress.retake.asked")}
            </span>
          )}
        </td>
        <td className="py-3 text-ink-muted">{student.email}</td>
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
        <td className="py-3 text-ink-muted text-xs">
          {relativeTime(student.last_activity, t)}
        </td>
      </tr>
      {isExpanded && (
        <tr>
          <td colSpan={8} className="p-0">
            {details}
          </td>
        </tr>
      )}
      {excuseModal}
    </>
  )
}

function Chevron({ open }: { open: boolean }) {
  return open ? (
    <ChevronDown className="h-4 w-4 text-ink-muted" strokeWidth={1.75} aria-hidden />
  ) : (
    <ChevronRight className="h-4 w-4 text-ink-muted" strokeWidth={1.75} aria-hidden />
  )
}

function SummaryStat({
  label,
  className,
  children,
}: {
  label: string
  className?: string
  children: React.ReactNode
}) {
  return (
    <div className={cn("min-w-0", className)}>
      <p className="text-xs text-ink-muted mb-1">{label}</p>
      {children}
    </div>
  )
}
