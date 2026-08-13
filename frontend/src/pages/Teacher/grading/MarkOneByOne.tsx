import { useCallback, useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { CheckCircle2, ChevronRight, Loader2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Textarea } from "@/components/ui/textarea"
import { Input } from "@/components/ui/input"
import { RubricGrid } from "@/components/rubric/RubricGrid"
import { gradesService } from "@/services/grades"
import { rubricsService } from "@/services/rubrics"
import { coursesService } from "@/services/courses"
import { getErrorDetail } from "@/lib/errorDetail"
import { toast } from "@/lib/toast"
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
  onDone,
}: {
  assignmentId: string
  title?: string
  onDone: () => void
}) {
  const { t } = useTranslation()
  const [work, setWork] = useState<WaitingSubmission[] | null>(null)
  const [index, setIndex] = useState(0)
  const [rubric, setRubric] = useState<SubmissionRubric | null>(null)
  const [grade, setGrade] = useState(0)
  const [feedback, setFeedback] = useState("")
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    let cancelled = false
    gradesService
      .getAssignmentQueue(assignmentId)
      .then((items) => {
        if (!cancelled) setWork(items)
      })
      .catch(() => {
        if (!cancelled) setWork([])
      })
    return () => {
      cancelled = true
    }
  }, [assignmentId])

  const current = work?.[index]

  useEffect(() => {
    if (!current) return
    let cancelled = false
    // Each piece of work starts clean. Carrying the previous student's note
    // into the next essay is the one mistake this screen must never make.
    setGrade(0)
    setFeedback("")
    setRubric(null)
    rubricsService
      .forSubmission(current.submission_id)
      .then((r) => {
        if (!cancelled) setRubric(r)
      })
      .catch(() => undefined)
    return () => {
      cancelled = true
    }
  }, [current])

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

  const saveAndNext = async () => {
    if (!current) return
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
          grade,
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
      <div className="flex items-baseline justify-between">
        <h2 className="truncate font-serif text-lg font-semibold">{title}</h2>
        {/* Where you are, so «дальше» is a known distance rather than an
            open-ended commitment on a Sunday evening. */}
        <span className="shrink-0 text-sm tabular-nums text-ink-muted">
          {index + 1} / {work.length}
        </span>
      </div>

      <Card>
        <CardContent className="space-y-3 p-4">
          <p className="text-xs text-ink-muted">{current.student_name}</p>
          {/* The work gets the screen — and the same reading treatment the
              chapters get. The product's careful typography used to stop at
              course text: the essay a teacher must actually read was set at
              14px at full card width, which is the one surface where an
              unreadable line length costs somebody an hour every week. */}
          <div className="prose whitespace-pre-wrap text-wrap-safe">{current.content}</div>
        </CardContent>
      </Card>

      {rubric?.rubric ? (
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
            value={grade}
            onChange={(e) => setGrade(Math.max(0, Number(e.target.value) || 0))}
            className="w-24"
            aria-label={t("grading.gradeAria")}
          />
          <span className="text-sm text-ink-muted">{t("grading.points")}</span>
        </div>
      )}

      <Textarea
        value={feedback}
        onChange={(e) => setFeedback(e.target.value)}
        placeholder={t("grading.feedbackPlaceholder")}
        className="min-h-[72px]"
      />

      <div className="flex items-center justify-end gap-2">
        <Button onClick={saveAndNext} disabled={saving} className="min-h-11">
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
