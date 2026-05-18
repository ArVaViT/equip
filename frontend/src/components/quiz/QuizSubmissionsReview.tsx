import { useCallback, useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { coursesService } from "@/services/courses"
import { toast } from "@/lib/toast"
import { getErrorDetail } from "@/lib/errorDetail"
import type { PendingAnswer } from "@/types"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import { Input } from "@/components/ui/input"
import { CheckCircle2, GraduationCap, Loader2, Save, Users } from "lucide-react"
import { formatDateTime } from "@/i18n/format"

type EditableAnswer = PendingAnswer & {
  draftPoints: string
  draftComment: string
  savingState: "idle" | "saving" | "saved"
}

function toDraft(answer: PendingAnswer): EditableAnswer {
  return {
    ...answer,
    draftPoints: String(answer.points_earned || ""),
    draftComment: answer.grader_comment ?? "",
    savingState: "idle",
  }
}

function countWords(text: string | null | undefined): number {
  if (!text) return 0
  return text.trim().split(/\s+/).filter(Boolean).length
}

interface Props {
  quizId: string
}

export default function QuizSubmissionsReview({ quizId }: Props) {
  const { t } = useTranslation()
  const [items, setItems] = useState<EditableAnswer[]>([])
  const [loading, setLoading] = useState(true)
  const [showGraded, setShowGraded] = useState(false)
  const [error, setError] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError(false)
    try {
      const pending = await coursesService.getPendingAnswers(quizId, showGraded)
      setItems(pending.map(toDraft))
    } catch {
      setError(true)
    } finally {
      setLoading(false)
    }
  }, [quizId, showGraded])

  useEffect(() => {
    void load()
  }, [load])

  const updateDraft = (id: string, patch: Partial<EditableAnswer>) => {
    setItems((prev) => prev.map((i) => (i.answer_id === id ? { ...i, ...patch } : i)))
  }

  const handleSave = async (item: EditableAnswer) => {
    const pointsNum = Number(item.draftPoints)
    if (Number.isNaN(pointsNum) || pointsNum < 0) {
      toast({ title: t("quizEditor.validation.validScoreRequired"), variant: "destructive" })
      return
    }
    if (pointsNum > item.max_points) {
      toast({
        title: t("quizEditor.validation.scoreCantExceed", { max: item.max_points }),
        variant: "destructive",
      })
      return
    }
    updateDraft(item.answer_id, { savingState: "saving" })
    try {
      await coursesService.gradeQuizAnswer(
        item.answer_id,
        pointsNum,
        item.draftComment.trim() || null,
      )
      updateDraft(item.answer_id, { savingState: "saved" })
      toast({ title: t("quizEditor.toast.gradeSaved"), variant: "success" })
      // Ungraded mode: drop the row from the list after a beat so the
      // teacher sees the success state before it disappears.
      if (!showGraded) {
        setTimeout(() => {
          setItems((prev) => prev.filter((i) => i.answer_id !== item.answer_id))
        }, 600)
      }
    } catch (err: unknown) {
      const detail = getErrorDetail(err)
      toast({
        title: detail || t("quizEditor.toast.gradeSaveFailed"),
        variant: "destructive",
      })
      updateDraft(item.answer_id, { savingState: "idle" })
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-8">
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" strokeWidth={1.75} />
      </div>
    )
  }

  if (error) {
    return (
      <p className="text-sm text-destructive py-4 text-center">
        {t("quizEditor.review.loadFailed")}
      </p>
    )
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Users className="h-4 w-4" strokeWidth={1.75} />
          {items.length === 0
            ? showGraded
              ? t("quizEditor.review.emptyAlready")
              : t("quizEditor.review.emptyAllGraded")
            : t("quizEditor.review.openEndedCount", { count: items.length })}
        </div>
        <label className="flex items-center gap-2 text-xs text-muted-foreground cursor-pointer select-none">
          <Checkbox
            checked={showGraded}
            onCheckedChange={(v) => setShowGraded(v === true)}
          />
          {t("quizEditor.review.showAlreadyGraded")}
        </label>
      </div>

      {items.map((item) => {
        const wordCount = countWords(item.text_answer)
        return (
          <div
            key={item.answer_id}
            className="rounded-md border bg-card p-4 space-y-3"
          >
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-wrap-safe whitespace-pre-line">
                  {item.question_text}
                </p>
                <div className="mt-1 flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
                  <span className="inline-flex items-center gap-1">
                    <GraduationCap className="h-3.5 w-3.5" strokeWidth={1.75} />
                    {item.question_type === "essay"
                      ? t("quizEditor.review.essay")
                      : t("quizEditor.review.shortAnswer")}{" "}
                    · {t("quizEditor.review.upToPoints", { count: item.max_points })}
                  </span>
                  {item.min_words ? (
                    <span
                      className={wordCount < item.min_words ? "text-warning" : undefined}
                    >
                      {t("quizEditor.review.wordsWithMin", { count: wordCount, min: item.min_words })}
                    </span>
                  ) : (
                    <span>{t("quizEditor.review.wordsCount", { count: wordCount })}</span>
                  )}
                </div>
              </div>
              <div className="text-right text-xs text-muted-foreground shrink-0">
                <div className="font-medium text-foreground">
                  {item.student_name || item.student_email}
                </div>
                {item.submitted_at && (
                  <div>{formatDateTime(item.submitted_at)}</div>
                )}
              </div>
            </div>

            <div className="rounded-md border border-dashed bg-muted/30 p-3 text-sm whitespace-pre-wrap text-wrap-safe">
              {item.text_answer || (
                <span className="text-muted-foreground italic">
                  {t("quizEditor.review.emptyAnswer")}
                </span>
              )}
            </div>

            <div className="flex flex-wrap items-end gap-3">
              <div className="space-y-1">
                <label className="text-xs text-muted-foreground">
                  {t("quizEditor.review.pointsLabel", { max: item.max_points })}
                </label>
                <Input
                  type="number"
                  min={0}
                  max={item.max_points}
                  value={item.draftPoints}
                  onChange={(e) => updateDraft(item.answer_id, { draftPoints: e.target.value })}
                  className="h-8 w-24 text-sm"
                />
              </div>
              <div className="flex-1 min-w-[220px] space-y-1">
                <label className="text-xs text-muted-foreground">
                  {t("quizEditor.review.commentLabel")}
                </label>
                <Input
                  value={item.draftComment}
                  onChange={(e) => updateDraft(item.answer_id, { draftComment: e.target.value })}
                  placeholder={t("quizEditor.review.commentPlaceholder")}
                  className="h-8 text-sm"
                />
              </div>
              <Button
                size="sm"
                onClick={() => handleSave(item)}
                disabled={item.savingState === "saving"}
              >
                {item.savingState === "saving" ? (
                  <Loader2 className="h-3.5 w-3.5 mr-1.5 animate-spin" strokeWidth={1.75} />
                ) : item.savingState === "saved" ? (
                  <CheckCircle2 className="h-3.5 w-3.5 mr-1.5" strokeWidth={1.75} />
                ) : (
                  <Save className="h-3.5 w-3.5 mr-1.5" strokeWidth={1.75} />
                )}
                {item.savingState === "saved"
                  ? t("quizEditor.review.saved")
                  : t("quizEditor.review.saveGrade")}
              </Button>
            </div>
          </div>
        )
      })}
    </div>
  )
}
