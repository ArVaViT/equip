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
  /** The draft differs from what is saved: said in the action bar. */
  dirty?: boolean
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
  dirty = false,
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

        {/* Said once for the quiz, not under every answered question: on a
            quiz a class has taken, ten copies of the same paragraph buried
            the questions. The locked type selector keeps it as a tooltip. */}
        {questions.some((q) => answeredQuestionIds.has(q.id)) && (
          <p className="text-xs text-ink-muted">{t("quizEditor.questions.typeLockedSummary")}</p>
        )}

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

      {/* Held at the bottom of the screen while the quiz scrolls: on a quiz
          of ten questions «Save» was 3,000px below the first one. Above the
          phone's tab bar (57px + safe area), flush to the edge from md. */}
      <div className="sticky bottom-[calc(57px+env(safe-area-inset-bottom))] z-10 -mx-4 flex flex-wrap items-center gap-2 border-t border-edge bg-surface px-4 py-3 md:bottom-0 sm:-mx-6 sm:px-6">
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
        {dirty && !saving && (
          <span className="text-xs text-ink-muted">{t("quizEditor.save.unsaved")}</span>
        )}
        {/* Quiet, and at the far end: a filled red button beside «Save»
            was one slip away from the class's attempts. */}
        {existingQuiz && (
          <Button
            size="sm"
            variant="ghost"
            className="text-destructive hover:text-destructive sm:ml-auto"
            onClick={onDelete}
            disabled={deleting}
            aria-label={chapterType === "exam" ? t("quizEditor.save.deleteExam") : t("quizEditor.save.deleteQuiz")}
          >
            {deleting ? (
              <Loader2 className="h-3.5 w-3.5 mr-1.5 animate-spin" strokeWidth={1.75} />
            ) : (
              <Trash2 className="h-3.5 w-3.5 sm:mr-1.5" strokeWidth={1.75} />
            )}
            {/* Icon only on a phone, where the words wrapped under the
                scroll-to-top button. */}
            <span className="hidden sm:inline">
              {chapterType === "exam"
                ? t("quizEditor.save.deleteExam")
                : t("quizEditor.save.deleteQuiz")}
            </span>
          </Button>
        )}
      </div>
    </>
  )
}
