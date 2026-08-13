import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { Card, CardContent } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Textarea } from "@/components/ui/textarea"
import { Badge } from "@/components/ui/badge"
import { FileText, Loader2, MessageSquare, Save, Star, User } from "lucide-react"
import { coursesService } from "@/services/courses"
import { rubricsService } from "@/services/rubrics"
import { RubricGrid } from "@/components/rubric/RubricGrid"
import { toast } from "@/lib/toast"
import { isHttpUrl } from "@/lib/url"
import type { AssignmentSubmission, SubmissionRubric } from "@/types"

interface Props {
  submission: AssignmentSubmission
  maxScore: number
  onUpdate: (updated: AssignmentSubmission) => void
}

type StatusVariant = "infoSubtle" | "successSubtle" | "warningSubtle" | "muted"

const STATUS_VARIANT: Record<string, StatusVariant> = {
  submitted: "infoSubtle",
  graded: "successSubtle",
  returned: "warningSubtle",
}

export function SubmissionGrader({ submission, maxScore, onUpdate }: Props) {
  const { t } = useTranslation()
  const [grade, setGrade] = useState(submission.grade ?? 0)
  const [feedback, setFeedback] = useState(submission.feedback ?? "")
  const [status, setStatus] = useState(submission.status)
  const [saving, setSaving] = useState(false)
  // The rubric, when the assignment is marked by one. `null` after loading
  // means it is not — which is a different screen from «rubric, nothing chosen».
  const [rubric, setRubric] = useState<SubmissionRubric | null>(null)

  useEffect(() => {
    let cancelled = false
    rubricsService
      .forSubmission(submission.id)
      .then((r) => {
        if (!cancelled) setRubric(r)
      })
      // An assignment without a rubric is the ordinary case today. A failure
      // here must not take the number field down with it.
      .catch(() => undefined)
    return () => {
      cancelled = true
    }
  }, [submission.id])

  const choose = async (criterionId: string, levelId: string) => {
    if (!rubric?.rubric) return
    const next = [
      ...rubric.marks.filter((m) => m.criterion_id !== criterionId),
      { criterion_id: criterionId, level_id: levelId, points: 0, comment: null },
    ]
    setSaving(true)
    try {
      const updated = await rubricsService.setMarks(
        submission.id,
        next.map((m) => ({ criterion_id: m.criterion_id, level_id: m.level_id })),
        feedback.trim() || undefined,
      )
      setRubric(updated)
      // The row above is told it was graded only when the grid is complete —
      // the same condition the server applies before it writes a number and
      // notifies the student. Announcing a grade the server did not write is
      // how the two sides start disagreeing about whether the student knows.
      const complete = updated.rubric?.criteria.every((c) =>
        updated.marks.some((m) => m.criterion_id === c.id),
      )
      if (complete && updated.earned !== null) {
        onUpdate({ ...submission, grade: updated.earned, status: "graded" })
      }
    } catch {
      toast({ title: t("rubric.saveFailed"), variant: "destructive" })
    } finally {
      setSaving(false)
    }
  }

  const save = async () => {
    setSaving(true)
    try {
      const updated = await coursesService.gradeSubmission(submission.id, {
        grade,
        feedback: feedback.trim() || undefined,
        status,
      })
      onUpdate(updated)
      toast({ title: t("assignmentEditor.toast.graded"), variant: "success" })
    } catch {
      toast({ title: t("assignmentEditor.toast.gradeFailed"), variant: "destructive" })
    } finally {
      setSaving(false)
    }
  }

  return (
    <Card className="bg-muted/20">
      <CardContent className="p-3 space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 text-sm">
            <User className="h-3.5 w-3.5 text-ink-muted" strokeWidth={1.75} />
            <span className="text-xs text-ink-muted">
              {submission.student_id.slice(0, 8)}...
            </span>
          </div>
          <Badge variant={STATUS_VARIANT[submission.status] ?? "muted"}>
            {t(`assignment.statusValue.${submission.status}`, {
              defaultValue: submission.status,
            })}
          </Badge>
        </div>

        {submission.content && (
          <div className="rounded border bg-surface p-2 text-sm whitespace-pre-wrap text-wrap-safe">
            {submission.content}
          </div>
        )}

        {submission.file_url && isHttpUrl(submission.file_url) && (
          <a
            href={submission.file_url}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1 text-xs text-info hover:underline"
          >
            <FileText className="h-3 w-3" strokeWidth={1.75} />
            {t("assignmentEditor.grader.viewFile")}
          </a>
        )}

        {rubric?.rubric && (
          <div className="rounded-md border border-edge bg-surface p-2.5">
            <p className="mb-2 text-xs font-medium text-ink-muted">{rubric.rubric.title}</p>
            <RubricGrid
              rubric={rubric.rubric}
              marks={rubric.marks}
              onChoose={choose}
              disabled={saving}
            />
          </div>
        )}

        {/* Hidden when a rubric decides the number: two ways to set one mark on
            one screen is an invitation to set them to different values, and the
            rubric is the one with a record of why. */}
        {!rubric?.rubric && (
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5">
            <Star className="h-3.5 w-3.5 text-ink-muted" strokeWidth={1.75} />
            <Input
              type="number"
              min={0}
              max={maxScore}
              value={grade}
              // Clamp into [0..maxScore] and fall back to 0 on empty/NaN.
              // Without this the teacher clearing the field lands NaN in
              // state, which JSON-serialises to ``null`` and trips the
              // backend's ``grade: int`` validation on save.
              onChange={(e) =>
                setGrade(Math.min(maxScore, Math.max(0, Number(e.target.value) || 0)))
              }
              fieldSize="sm"
              className="w-20"
            />
            <span className="text-xs text-ink-muted">/ {maxScore}</span>
          </div>
          <Select
            value={status}
            onValueChange={(v) => setStatus(v as AssignmentSubmission["status"])}
          >
            <SelectTrigger
              size="xs"
              aria-label={t("assignmentEditor.grader.statusAria")}
              className="w-auto"
            >
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="graded">{t("assignmentEditor.grader.statusGrade")}</SelectItem>
              <SelectItem value="returned">{t("assignmentEditor.grader.statusReturn")}</SelectItem>
            </SelectContent>
          </Select>
        </div>
        )}

        <div className="space-y-1">
          <Label className="text-xs flex items-center gap-1">
            <MessageSquare className="h-3 w-3" strokeWidth={1.75} />
            {t("assignmentEditor.grader.feedback")}
          </Label>
          <Textarea
            fieldSize="sm"
            value={feedback}
            onChange={(e) => setFeedback(e.target.value)}
            placeholder={t("assignmentEditor.grader.feedbackPlaceholder")}
            className="min-h-[50px] text-xs"
          />
        </div>

        <Button size="sm" className="h-7 text-xs" onClick={save} disabled={saving}>
          {saving ? (
            <Loader2 className="h-3 w-3 mr-1 animate-spin" strokeWidth={1.75} />
          ) : (
            <Save className="h-3 w-3 mr-1" strokeWidth={1.75} />
          )}
          {saving ? t("assignmentEditor.grader.saving") : t("assignmentEditor.grader.save")}
        </Button>
      </CardContent>
    </Card>
  )
}
