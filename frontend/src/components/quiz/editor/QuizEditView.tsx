import { ListPlus, Loader2, Plus, Save, Trash2 } from "lucide-react"
import { useTranslation } from "react-i18next"
import { Button } from "@/components/ui/button"
import { EmptyState } from "@/components/patterns"
import type { Quiz } from "@/types"
import { QuestionCard } from "./QuestionCard"
import { QuizHeaderFields } from "./QuizHeaderFields"
import type { DraftOption, DraftQuestion } from "./types"

interface Props {
  title: string
  setTitle: (v: string) => void
  description: string
  setDescription: (v: string) => void
  passingScore: number
  setPassingScore: (v: number) => void
  maxAttempts: number
  setMaxAttempts: (v: number) => void
  chapterType: "quiz" | "exam"
  questions: DraftQuestion[]
  onAddQuestion: () => void
  onRemoveQuestion: (idx: number) => void
  onMoveQuestion: (idx: number, direction: "up" | "down") => void
  onUpdateQuestion: (idx: number, patch: Partial<DraftQuestion>) => void
  onAddOption: (qIdx: number) => void
  onRemoveOption: (qIdx: number, oIdx: number) => void
  onUpdateOption: (qIdx: number, oIdx: number, patch: Partial<DraftOption>) => void
  saving: boolean
  onSave: () => void
  existingQuiz: Quiz | null
  /** Questions students have already answered — their type is fixed. */
  answeredQuestionIds?: ReadonlySet<string>
  deleting: boolean
  onDelete: () => void
}

const NONE: ReadonlySet<string> = new Set()

export function QuizEditView({
  title,
  setTitle,
  description,
  setDescription,
  passingScore,
  setPassingScore,
  maxAttempts,
  setMaxAttempts,
  chapterType,
  questions,
  onAddQuestion,
  onRemoveQuestion,
  onMoveQuestion,
  onUpdateQuestion,
  onAddOption,
  onRemoveOption,
  onUpdateOption,
  saving,
  onSave,
  existingQuiz,
  answeredQuestionIds = NONE,
  deleting,
  onDelete,
}: Props) {
  const { t } = useTranslation()
  return (
    <>
      <QuizHeaderFields
        title={title}
        setTitle={setTitle}
        description={description}
        setDescription={setDescription}
        passingScore={passingScore}
        setPassingScore={setPassingScore}
        maxAttempts={maxAttempts}
        setMaxAttempts={setMaxAttempts}
        chapterType={chapterType}
      />

      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <span className="text-sm font-medium">
            {t("quizEditor.questions.heading", { count: questions.length })}
          </span>
          <Button variant="outline" size="sm" onClick={onAddQuestion} className="h-7 text-xs">
            <Plus className="h-3 w-3 mr-1" strokeWidth={1.75} />
            {t("quizEditor.questions.addQuestion")}
          </Button>
        </div>

        {questions.map((q, qIdx) => (
          <QuestionCard
            key={q.id}
            question={q}
            index={qIdx}
            total={questions.length}
            typeLocked={answeredQuestionIds.has(q.id)}
            onRemove={() => onRemoveQuestion(qIdx)}
            onMove={(dir) => onMoveQuestion(qIdx, dir)}
            onUpdate={(patch) => onUpdateQuestion(qIdx, patch)}
            onAddOption={() => onAddOption(qIdx)}
            onRemoveOption={(oIdx) => onRemoveOption(qIdx, oIdx)}
            onUpdateOption={(oIdx, patch) => onUpdateOption(qIdx, oIdx, patch)}
          />
        ))}

        {questions.length === 0 && (
          <EmptyState
            icon={<ListPlus strokeWidth={1.75} aria-hidden />}
            title={t("quizEditor.questions.emptyTitle")}
            description={t("quizEditor.questions.empty")}
          />
        )}
      </div>

      <div className="flex items-center gap-2 pt-2">
        <Button size="sm" onClick={onSave} disabled={saving}>
          {saving ? (
            <Loader2 className="h-3.5 w-3.5 mr-1.5 animate-spin" strokeWidth={1.75} />
          ) : (
            <Save className="h-3.5 w-3.5 mr-1.5" strokeWidth={1.75} />
          )}
          {saving
            ? t("quizEditor.save.saving")
            : chapterType === "exam"
              ? t("quizEditor.save.saveExam")
              : t("quizEditor.save.saveQuiz")}
        </Button>
        {existingQuiz && (
          <Button size="sm" variant="destructive" onClick={onDelete} disabled={deleting}>
            {deleting ? (
              <Loader2 className="h-3.5 w-3.5 mr-1.5 animate-spin" strokeWidth={1.75} />
            ) : (
              <Trash2 className="h-3.5 w-3.5 mr-1.5" strokeWidth={1.75} />
            )}
            {chapterType === "exam"
              ? t("quizEditor.save.deleteExam")
              : t("quizEditor.save.deleteQuiz")}
          </Button>
        )}
      </div>
    </>
  )
}
