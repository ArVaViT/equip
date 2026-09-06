import { useState } from "react"
import { useTranslation } from "react-i18next"
import { ClipboardList, Loader2 } from "lucide-react"
import { useConfirm } from "@/components/ui/alert-dialog"
import { coursesService } from "@/services/courses"
import { getErrorDetail } from "@/lib/errorDetail"
import { toast } from "@/lib/toast"
import type { Quiz } from "@/types"
import QuizSubmissionsReview from "./QuizSubmissionsReview"
import {
  ModeToggle,
  QuizEditView,
  firstDraftProblem,
  isEmptyPlan,
  planInPlaceSave,
  useQuizDraft,
  type DraftSnapshot,
  type InPlacePlan,
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

  const snapshot = (): DraftSnapshot => ({
    title: draft.title.trim(),
    description: draft.description.trim() || null,
    passingScore: draft.passingScore,
    maxAttempts: chapterType === "exam" ? draft.maxAttempts : null,
    questions: draft.questions,
  })

  const createFromDraft = (shape: DraftSnapshot) =>
    coursesService.createQuiz({
      chapter_id: chapterId,
      title: shape.title,
      description: shape.description,
      quiz_type: chapterType,
      max_attempts: shape.maxAttempts,
      passing_score: shape.passingScore,
      questions: shape.questions.map((q) => ({
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

  /**
   * Corrections go to the quiz that exists. Each route answers with the
   * whole quiz re-read, so the last answer is the new baseline; sent one
   * after another so a refusal (a type change on an answered question,
   * 409) stops the run where it happened and the draft stays as typed.
   */
  const applyInPlace = async (existing: Quiz, plan: InPlacePlan): Promise<Quiz> => {
    let latest = existing
    if (plan.quiz) latest = await coursesService.updateQuiz(existing.id, plan.quiz, chapterId)
    for (const { id, patch } of plan.questions) {
      latest = await coursesService.updateQuizQuestion(id, patch, chapterId)
    }
    for (const { id, patch } of plan.options) {
      latest = await coursesService.updateQuizOption(id, patch, chapterId)
    }
    return latest
  }

  const handleSave = async () => {
    if (!draft.title.trim()) {
      toast({ title: t("quizEditor.validation.titleRequired"), variant: "destructive" })
      return
    }
    if (draft.questions.length === 0) {
      toast({ title: t("quizEditor.validation.addAtLeastOneQuestion"), variant: "destructive" })
      return
    }
    const problem = firstDraftProblem(draft.questions)
    if (problem) {
      toast({ title: problem, variant: "destructive" })
      return
    }

    const shape = snapshot()
    const existing = draft.existingQuiz
    const plan = existing ? planInPlaceSave(existing, shape) : null

    // Adding or removing a question or an option is a rebuild — the only
    // shape the in-place routes cannot reach — and a rebuild deletes every
    // attempt. With attempts on the quiz, the teacher decides, knowing the
    // number; without, there is nothing to lose.
    if (existing && !plan && draft.attemptCount > 0) {
      const ok = await confirm({
        title: t("quizEditor.confirmRebuild.title"),
        description: t("quizEditor.confirmRebuild.description", { count: draft.attemptCount }),
        confirmLabel: t("quizEditor.confirmRebuild.confirm"),
        tone: "destructive",
      })
      if (!ok) return
    }

    setSaving(true)
    try {
      if (existing && plan) {
        const quiz = isEmptyPlan(plan) ? existing : await applyInPlace(existing, plan)
        draft.setExistingQuiz(quiz)
        onQuizSaved?.(quiz.id)
        toast({ title: t("quizEditor.toast.quizSaved"), variant: "success" })
        return
      }

      const quiz = await createFromDraft(shape)
      draft.setExistingQuiz(quiz)
      draft.clearAttempts()
      onQuizSaved?.(quiz.id)
      draft.setMaxAttempts(quiz.max_attempts ?? (chapterType === "exam" ? 1 : 3))
      if (existing) {
        // The new quiz is saved; the old one goes only after the teacher
        // has agreed to lose its attempts (``force``). If the delete is
        // refused all the same — a student finished an attempt in between
        // — say so rather than leave two quizzes on the chapter in silence.
        try {
          await coursesService.deleteQuiz(existing.id, chapterId, { force: draft.attemptCount > 0 })
        } catch (err) {
          toast({
            title: t("quizEditor.toast.oldQuizNotDeleted"),
            description: getErrorDetail(err),
            variant: "destructive",
          })
          return
        }
      }
      toast({ title: t("quizEditor.toast.quizSaved"), variant: "success" })
    } catch (err) {
      toast({
        title: t("quizEditor.toast.quizSaveFailed"),
        description: getErrorDetail(err),
        variant: "destructive",
      })
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async () => {
    if (!draft.existingQuiz) return
    const attempts = draft.attemptCount
    const ok = await confirm({
      title: t("quizEditor.confirmDelete.title"),
      description:
        attempts > 0
          ? t("quizEditor.confirmDelete.withAttempts", { count: attempts })
          : t("quizEditor.confirmDelete.description"),
      confirmLabel: t("quizEditor.confirmDelete.confirm"),
      tone: "destructive",
    })
    if (!ok) return
    setDeleting(true)
    try {
      await coursesService.deleteQuiz(draft.existingQuiz.id, chapterId, { force: attempts > 0 })
      draft.resetAll()
      toast({ title: t("quizEditor.toast.quizDeleted"), variant: "success" })
    } catch (err) {
      toast({
        title: t("quizEditor.toast.quizDeleteFailed"),
        description: getErrorDetail(err),
        variant: "destructive",
      })
    } finally {
      setDeleting(false)
    }
  }

  if (draft.loading) {
    return (
      <div className="flex items-center justify-center py-8">
        <Loader2 className="h-5 w-5 animate-spin text-ink-muted" strokeWidth={1.75} />
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
          <ClipboardList className="h-4 w-4 text-ink-muted" strokeWidth={1.75} />
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
          answeredQuestionIds={draft.answeredQuestionIds}
          deleting={deleting}
          onDelete={handleDelete}
        />
      )}
    </div>
  )
}
