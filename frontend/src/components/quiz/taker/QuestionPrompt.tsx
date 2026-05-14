import { useTranslation } from "react-i18next"
import type { QuizQuestion } from "@/types"
import { EssayAnswer } from "./EssayAnswer"
import type { QuizAnswer } from "./types"
import { Textarea } from "@/components/ui/textarea"
import { getTrueFalseLabel } from "@/components/quiz/editor/types"

interface Props {
  question: QuizQuestion
  index: number
  answer?: QuizAnswer
  onAnswer: (val: QuizAnswer) => void
}

export function QuestionPrompt({ question, index, answer, onAnswer }: Props) {
  const { t } = useTranslation()
  const sortedOptions = [...(question.options ?? [])].sort(
    (a, b) => a.order_index - b.order_index,
  )

  return (
    <div className="space-y-3">
      <div className="flex items-start gap-2">
        <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary/10 text-xs font-semibold text-primary">
          {index + 1}
        </span>
        <div className="min-w-0 flex-1 text-wrap-safe">
          <p className="text-sm font-medium whitespace-pre-line">
            {question.question_text}
          </p>
          <span className="text-xs text-muted-foreground">
            {t("quiz.questionPoints", { count: question.points })}
          </span>
        </div>
      </div>

      {question.question_type === "multiple_choice" && (
        <div className="ml-8 space-y-2">
          {sortedOptions.map((opt) => (
            <label
              key={opt.id}
              className={`flex items-center gap-3 px-3 py-2.5 rounded-md border cursor-pointer transition-colors ${
                answer?.selected_option_id === opt.id
                  ? "border-primary bg-primary/5"
                  : "border-border hover:bg-muted/50"
              }`}
            >
              <input
                type="radio"
                name={`q-${question.id}`}
                checked={answer?.selected_option_id === opt.id}
                onChange={() => onAnswer({ selected_option_id: opt.id })}
                className="accent-primary"
              />
              <span className="text-sm">{opt.option_text}</span>
            </label>
          ))}
        </div>
      )}

      {question.question_type === "true_false" && (
        <div className="ml-8 flex gap-3">
          {sortedOptions.map((opt) => (
            <button
              key={opt.id}
              type="button"
              onClick={() => onAnswer({ selected_option_id: opt.id })}
              className={`flex-1 py-2.5 rounded-md border text-sm font-medium transition-colors ${
                answer?.selected_option_id === opt.id
                  ? "border-primary bg-primary/10 text-primary"
                  : "border-border hover:bg-muted/50"
              }`}
            >
              {getTrueFalseLabel(opt.option_text, t)}
            </button>
          ))}
        </div>
      )}

      {question.question_type === "short_answer" && (
        <div className="ml-8">
          <Textarea
            fieldSize="default"
            value={answer?.text_answer ?? ""}
            onChange={(e) => onAnswer({ text_answer: e.target.value })}
            placeholder={t("quiz.typeAnswerPlaceholder")}
          />
        </div>
      )}

      {question.question_type === "essay" && (
        <EssayAnswer
          value={answer?.text_answer ?? ""}
          minWords={question.min_words}
          onChange={(text) => onAnswer({ text_answer: text })}
        />
      )}
    </div>
  )
}
