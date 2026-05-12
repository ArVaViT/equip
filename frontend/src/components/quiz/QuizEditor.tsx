import { useState } from "react"
import { useTranslation } from "react-i18next"
import { ClipboardList, Loader2 } from "lucide-react"
import { useConfirm } from "@/components/ui/alert-dialog"
import { coursesService } from "@/services/courses"
import { toast } from "@/lib/toast"
import QuizSubmissionsReview from "./QuizSubmissionsReview"
import {
  ModeToggle,
  QuizEditView,
  useQuizDraft,
  type QuizEditorMode,
} from "./editor"

interface QuizEditorProps {
  chapterId: string
  chapterType?: "quiz" | "exam"
  onQuizSaved?: (quizId: string) => void
}

export default function QuizEditor({
  chapterId,
  chapterType = "quiz",
  onQuizSaved,
}: QuizEditorProps) {
  const confirm = useConfirm()
  const { t } = useTranslation()
  const draft = useQuizDraft({ chapterId, chapterType })
  const [saving, setSaving] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [mode, setMode] = useState<QuizEditorMode>("edit")

  const handleSave = async () => {
    if (!draft.title.trim()) {
      toast({ title: t("quizEditor.validation.titleRequired"), variant: "destructive" })
      return
    }
    if (draft.questions.length === 0) {
      toast({ title: t("quizEditor.validation.addAtLeastOneQuestion"), variant: "destructive" })
      return
    }

    setSaving(true)
    try {
      const oldQuizId = draft.existingQuiz?.id
      const quiz = await coursesService.createQuiz({
        chapter_id: chapterId,
        title: draft.title.trim(),
        description: draft.description.trim() || null,
        quiz_type: chapterType,
        max_attempts: chapterType === "exam" ? draft.maxAttempts : null,
        passing_score: draft.passingScore,
        questions: draft.questions.map((q) => ({
          question_text: q.question_text,
          question_type: q.question_type,
          order_index: q.order_index,
          points: q.points,
          min_words: q.question_type === "essay" ? (q.min_words ?? null) : null,
          options: q.options.map((o) => ({
            option_text: o.option_text,
            is_correct: o.is_correct,
            order_index: o.order_index,
          })),
        })),
      })
      draft.setExistingQuiz(quiz)
      onQuizSaved?.(quiz.id)
      draft.setMaxAttempts(quiz.max_attempts ?? (chapterType === "exam" ? 1 : 3))
      if (oldQuizId) {
        await coursesService.deleteQuiz(oldQuizId, chapterId).catch(() => {
          // Old quiz cleanup is best-effort; the new quiz was already saved
        })
      }
      toast({ title: t("quizEditor.toast.quizSaved"), variant: "success" })
    } catch {
      toast({ title: t("quizEditor.toast.quizSaveFailed"), variant: "destructive" })
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async () => {
    if (!draft.existingQuiz) return
    const ok = await confirm({
      title: t("quizEditor.confirmDelete.title"),
      description: t("quizEditor.confirmDelete.description"),
      confirmLabel: t("quizEditor.confirmDelete.confirm"),
      tone: "destructive",
    })
    if (!ok) return
    setDeleting(true)
    try {
      await coursesService.deleteQuiz(draft.existingQuiz.id, chapterId)
      draft.resetAll()
      toast({ title: t("quizEditor.toast.quizDeleted"), variant: "success" })
    } catch {
      toast({ title: t("quizEditor.toast.quizDeleteFailed"), variant: "destructive" })
    } finally {
      setDeleting(false)
    }
  }

  if (draft.loading) {
    return (
      <div className="flex items-center justify-center py-8">
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
      </div>
    )
  }

  const hasManualQuestions =
    draft.existingQuiz?.questions.some(
      (q) => q.question_type === "short_answer" || q.question_type === "essay",
    ) ?? false

  return (
    <div className="space-y-4 mt-3">
      <div className="flex items-center justify-between gap-2 mb-2">
        <div className="flex items-center gap-2">
          <ClipboardList className="h-4 w-4 text-muted-foreground" />
          <span className="text-sm font-medium">
            {draft.existingQuiz
              ? chapterType === "exam"
                ? t("quizEditor.heading.editExam")
                : t("quizEditor.heading.editQuiz")
              : chapterType === "exam"
                ? t("quizEditor.heading.createExam")
                : t("quizEditor.heading.createQuiz")}
          </span>
        </div>
        {draft.existingQuiz && hasManualQuestions && (
          <ModeToggle mode={mode} setMode={setMode} />
        )}
      </div>

      {mode === "review" && draft.existingQuiz ? (
        <QuizSubmissionsReview quizId={draft.existingQuiz.id} />
      ) : (
        <QuizEditView
          title={draft.title}
          setTitle={draft.setTitle}
          description={draft.description}
          setDescription={draft.setDescription}
          passingScore={draft.passingScore}
          setPassingScore={draft.setPassingScore}
          maxAttempts={draft.maxAttempts}
          setMaxAttempts={draft.setMaxAttempts}
          chapterType={chapterType}
          questions={draft.questions}
          onAddQuestion={draft.addQuestion}
          onRemoveQuestion={draft.removeQuestion}
          onMoveQuestion={draft.moveQuestion}
          onUpdateQuestion={draft.updateQuestion}
          onAddOption={draft.addOption}
          onRemoveOption={draft.removeOption}
          onUpdateOption={draft.updateOption}
          saving={saving}
          onSave={handleSave}
          existingQuiz={draft.existingQuiz}
          deleting={deleting}
          onDelete={handleDelete}
        />
      )}
    </div>
  )
}
