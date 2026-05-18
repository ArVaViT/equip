import { useState } from "react"
import { useTranslation } from "react-i18next"
import { Card, CardContent } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { NativeSelect } from "@/components/ui/native-select"
import { Textarea } from "@/components/ui/textarea"
import { Badge } from "@/components/ui/badge"
import { FileText, Loader2, MessageSquare, Save, Star, User } from "lucide-react"
import { coursesService } from "@/services/courses"
import { toast } from "@/lib/toast"
import type { AssignmentSubmission } from "@/types"

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
            <User className="h-3.5 w-3.5 text-muted-foreground" strokeWidth={1.75} />
            <span className="text-xs text-muted-foreground">
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
          <div className="rounded border bg-background p-2 text-sm whitespace-pre-wrap text-wrap-safe">
            {submission.content}
          </div>
        )}

        {submission.file_url && (
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

        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5">
            <Star className="h-3.5 w-3.5 text-muted-foreground" strokeWidth={1.75} />
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
            <span className="text-xs text-muted-foreground">/ {maxScore}</span>
          </div>
          <NativeSelect
            fieldSize="xs"
            value={status}
            aria-label={t("assignmentEditor.grader.statusAria")}
            onChange={(e) => setStatus(e.target.value as AssignmentSubmission["status"])}
            className="w-auto"
          >
            <option value="graded">{t("assignmentEditor.grader.statusGrade")}</option>
            <option value="returned">{t("assignmentEditor.grader.statusReturn")}</option>
          </NativeSelect>
        </div>

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
