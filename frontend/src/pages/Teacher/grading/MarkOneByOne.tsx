import { useCallback, useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { CheckCircle2, ChevronRight, FileText, Loader2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Textarea } from "@/components/ui/textarea"
import { Input } from "@/components/ui/input"
import { RubricGrid } from "@/components/rubric/RubricGrid"
import { ErrorState, LateBadge } from "@/components/patterns"
import { gradesService } from "@/services/grades"
import { rubricsService } from "@/services/rubrics"
import { coursesService } from "@/services/courses"
import { getErrorDetail } from "@/lib/errorDetail"
import { toast } from "@/lib/toast"
import { isHttpUrl } from "@/lib/url"
import type { SubmissionRubric, WaitingSubmission } from "@/types"

/**
 * One prompt, everyone's answers, one at a time.
 *
 * The screen belongs to the work. Everything else — the rubric, the note, the
 * next button — is one tap away and nothing needs typing on a phone unless the
 * teacher wants to write something. A bivocational pastor marking on Sunday
 * evening is the case this has to survive; typing on a phone is why marking
 * gets postponed and then not done.
 *
 * «Дальше» is the primary action and it saves. A queue you have to
 * save-and-go-back through is a queue you leave half-done.
 */
export function MarkOneByOne({
  assignmentId,
  title,
  maxScore = null,
  onDone,
}: {
  assignmentId: string
  title?: string
  maxScore?: number | null
  onDone: () => void
}) {
  const { t } = useTranslation()
  const [work, setWork] = useState<WaitingSubmission[] | null>(null)
  const [index, setIndex] = useState(0)
  const [rubric, setRubric] = useState<SubmissionRubric | null>(null)
  // Empty until the teacher types a mark. It started at 0, so «Сохранить»
  // on an essay nobody had scored yet sent the student a zero.
  const [grade, setGrade] = useState<number | null>(null)
  const [feedback, setFeedback] = useState("")
  const [saving, setSaving] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [loadAttempt, setLoadAttempt] = useState(0)
  const [rubricFailed, setRubricFailed] = useState(false)
  const [rubricAttempt, setRubricAttempt] = useState(0)

  useEffect(() => {
    let cancelled = false
    setLoadError(null)
    gradesService
      .getAssignmentQueue(assignmentId)
      .then((items) => {
        if (!cancelled) setWork(items)
      })
      .catch((err: unknown) => {
        // Not `[]`. An empty queue renders the green «all marked» card, and a
        // queue that did not load — a 403 on somebody else's course, a
        // dropped connection — is not one the teacher has finished.
        if (!cancelled) setLoadError(getErrorDetail(err, t("grading.loadFailed")))
      })
    return () => {
      cancelled = true
    }
  }, [assignmentId, loadAttempt, t])

  const current = work?.[index]

  useEffect(() => {
    if (!current) return
    let cancelled = false
    // Each piece of work starts clean. Carrying the previous student's note
    // into the next essay is the one mistake this screen must never make.
    setGrade(null)
    setFeedback("")
    setRubric(null)
    setRubricFailed(false)
    rubricsService
      .forSubmission(current.submission_id)
      .then((r) => {
        if (!cancelled) setRubric(r)
      })
      .catch(() => {
        // Without an answer the screen would fall back to the bare number
        // box — and a number where the course uses a rubric is a different
        // mark than the teacher meant to give. Say so and wait.
        if (!cancelled) setRubricFailed(true)
      })
    return () => {
      cancelled = true
    }
  }, [current, rubricAttempt])

  const advance = useCallback(() => {
    if (!work) return
    if (index + 1 >= work.length) onDone()
    else setIndex((i) => i + 1)
  }, [index, work, onDone])

  const chooseLevel = async (criterionId: string, levelId: string) => {
    if (!current || !rubric?.rubric) return
    const next = [
      ...rubric.marks.filter((m) => m.criterion_id !== criterionId),
      { criterion_id: criterionId, level_id: levelId, points: 0, comment: null },
    ]
    try {
      setRubric(
        await rubricsService.setMarks(
          current.submission_id,
          next.map((m) => ({ criterion_id: m.criterion_id, level_id: m.level_id })),
          feedback.trim() || undefined,
        ),
      )
    } catch (err) {
      toast({ title: getErrorDetail(err, t("rubric.saveFailed")), variant: "destructive" })
    }
  }

  // Until the rubric answer arrives the screen cannot know which kind of
  // mark this course takes; a number typed in that moment would land where a
  // rubric was meant.
  const rubricLoading = rubric === null && !rubricFailed
  const overMax = maxScore != null && grade != null && grade > maxScore
  // With a rubric the mark is the levels chosen: every criterion needs one,
  // or «Сохранить и закончить» moved on from an essay nobody had marked —
  // the rubric writes as levels are picked, and an untouched one wrote
  // nothing (2026-10-03).
  // Counted per criterion, not by number of marks: re-attaching a rubric keeps
  // the old one's marks, and they would make up the count.
  const rubricIncomplete =
    rubric?.rubric != null &&
    !rubric.rubric.criteria.every((c) => rubric.marks.some((m) => m.criterion_id === c.id))
  const needsMark = rubricLoading || rubricIncomplete || (!rubric?.rubric && (grade === null || overMax))

  const saveAndNext = async () => {
    if (!current || needsMark) return
    setSaving(true)
    try {
      if (rubric?.rubric) {
        // The rubric already wrote the mark as levels were chosen; this only
        // carries the note, and only if there is one.
        if (feedback.trim()) {
          await rubricsService.setMarks(
            current.submission_id,
            rubric.marks.map((m) => ({ criterion_id: m.criterion_id, level_id: m.level_id })),
            feedback.trim(),
          )
        }
      } else {
        await coursesService.gradeSubmission(current.submission_id, {
          grade: grade ?? 0,
          feedback: feedback.trim() || undefined,
          status: "graded",
        })
      }
      advance()
    } catch (err) {
      toast({ title: getErrorDetail(err, t("grading.saveFailed")), variant: "destructive" })
    } finally {
      setSaving(false)
    }
  }

  if (loadError) {
    return (
      <ErrorState
        description={loadError}
        action={
          <Button size="sm" variant="outline" onClick={() => setLoadAttempt((n) => n + 1)}>
            {t("common.tryAgain")}
          </Button>
        }
        secondaryAction={
          <Button size="sm" variant="ghost" onClick={onDone}>
            {t("grading.backToQueue")}
          </Button>
        }
      />
    )
  }

  if (work === null) {
    return (
      <div className="flex items-center gap-2 py-8 text-sm text-ink-muted">
        <Loader2 className="h-4 w-4 animate-spin" strokeWidth={1.75} aria-hidden />
        {t("common.loading")}
      </div>
    )
  }

  if (!current) {
    return (
      <Card>
        <CardContent className="flex flex-col items-center gap-2 py-10 text-center">
          <CheckCircle2 className="h-8 w-8 text-success" strokeWidth={1.75} aria-hidden />
          <p className="font-medium">{t("grading.groupDoneTitle")}</p>
          <Button size="sm" variant="outline" onClick={onDone}>
            {t("grading.backToQueue")}
          </Button>
        </CardContent>
      </Card>
    )
  }

  return (
    <div className="space-y-3">
      <div className="flex items-baseline justify-between gap-3">
        <h2 className="line-clamp-2 min-w-0 break-words font-serif text-lg font-semibold">{title}</h2>
        {/* Where you are, so «дальше» is a known distance rather than an
            open-ended commitment on a Sunday evening. */}
        <span className="shrink-0 text-sm tabular-nums text-ink-muted">
          {index + 1} / {work.length}
        </span>
      </div>

      <Card>
        <CardContent className="space-y-3 p-4">
          <p className="flex items-center gap-2 text-xs text-ink-muted">
            {current.student_name}
            {current.is_late && <LateBadge />}
          </p>
          {/* The work gets the screen — and the same reading treatment the
              chapters get. The product's careful typography used to stop at
              course text: the essay a teacher must actually read was set at
              14px at full card width, which is the one surface where an
              unreadable line length costs somebody an hour every week. */}
          <div className="prose whitespace-pre-wrap text-wrap-safe">{current.content}</div>
          {/* The file the student linked. This screen never showed it, so
              work handed in as a document read as an empty essay. */}
          {current.file_url && isHttpUrl(current.file_url) && (
            <a
              href={current.file_url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex min-h-11 items-center gap-1.5 text-sm text-info hover:underline"
            >
              <FileText className="h-4 w-4 shrink-0" strokeWidth={1.75} aria-hidden />
              {t("assignmentEditor.grader.viewFile")}
            </a>
          )}
        </CardContent>
      </Card>

      {rubricFailed ? (
        <ErrorState
          className="py-6"
          title={t("rubric.loadFailed")}
          description={t("rubric.loadFailedBody")}
          action={
            <Button size="sm" variant="outline" onClick={() => setRubricAttempt((n) => n + 1)}>
              {t("common.tryAgain")}
            </Button>
          }
        />
      ) : rubricLoading ? null : rubric?.rubric ? (
        <Card>
          <CardContent className="p-4">
            <RubricGrid
              rubric={rubric.rubric}
              marks={rubric.marks}
              onChoose={chooseLevel}
              disabled={saving}
            />
          </CardContent>
        </Card>
      ) : (
        <div className="flex items-center gap-2">
          <Input
            type="number"
            min={0}
            max={maxScore ?? undefined}
            step={1}
            value={grade ?? ""}
            // Whole points: the grade route takes an integer, and 9.5 came
            // back as a raw validation error.
            onChange={(e) =>
              setGrade(e.target.value === "" ? null : Math.max(0, Math.floor(Number(e.target.value) || 0)))
            }
            aria-invalid={overMax || undefined}
            className={overMax ? "w-24 border-destructive" : "w-24"}
            aria-label={t("grading.gradeAria")}
          />
          <span className="text-sm text-ink-muted">
            {maxScore ? t("grading.outOf", { max: maxScore }) : t("grading.points")}
          </span>
        </div>
      )}

      <Textarea
        value={feedback}
        onChange={(e) => setFeedback(e.target.value)}
        placeholder={t("grading.feedbackPlaceholder")}
        className="min-h-[72px]"
      />

      <div className="flex items-center justify-end gap-2">
        <Button onClick={saveAndNext} disabled={saving || rubricFailed || needsMark} className="min-h-11">
          {saving ? (
            <Loader2 className="mr-1.5 h-4 w-4 animate-spin" strokeWidth={1.75} aria-hidden />
          ) : (
            <ChevronRight className="mr-1.5 h-4 w-4" strokeWidth={1.75} aria-hidden />
          )}
          {index + 1 >= work.length ? t("grading.saveAndFinish") : t("grading.saveAndNext")}
        </Button>
      </div>
    </div>
  )
}
