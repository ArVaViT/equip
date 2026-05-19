import { useTranslation } from "react-i18next"
import type { QuizQuestion } from "@/types"
import { EssayAnswer } from "./EssayAnswer"
import type { QuizAnswer } from "./types"
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group"
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
      <div className="flex items-start gap-3">
        <span
          aria-hidden
          className="mt-0.5 inline-flex h-6 min-w-[1.5rem] shrink-0 items-center justify-center rounded-md border border-border bg-muted/60 px-1.5 text-xs font-medium tabular-nums text-muted-foreground"
        >
          {index + 1}
        </span>
        <div className="min-w-0 flex-1 text-wrap-safe">
          <p className="text-sm font-medium leading-relaxed whitespace-pre-line">
            {question.question_text}
          </p>
          <span className="mt-1 inline-block text-xs text-muted-foreground tabular-nums">
            {t("quiz.questionPoints", { count: question.points })}
          </span>
        </div>
      </div>

      {question.question_type === "multiple_choice" && (
        <RadioGroup
          className="ml-9 space-y-2"
          value={answer?.selected_option_id ?? ""}
          onValueChange={(v) => onAnswer({ selected_option_id: v })}
        >
          {sortedOptions.map((opt) => (
            <label
              key={opt.id}
              htmlFor={`q-${question.id}-${opt.id}`}
              className={`flex cursor-pointer items-center gap-3 rounded-md border px-3 py-2.5 transition-colors ${
                answer?.selected_option_id === opt.id
                  ? "border-primary/60 bg-primary/5 ring-1 ring-primary/30"
                  : "border-border hover:bg-muted/40"
              }`}
            >
              <RadioGroupItem id={`q-${question.id}-${opt.id}`} value={opt.id} />
              <span className="text-sm text-wrap-safe">{opt.option_text}</span>
            </label>
          ))}
        </RadioGroup>
      )}

      {question.question_type === "true_false" && (
        <div className="ml-9 grid grid-cols-2 gap-2">
          {sortedOptions.map((opt) => (
            <button
              key={opt.id}
              type="button"
              onClick={() => onAnswer({ selected_option_id: opt.id })}
              className={`rounded-md border px-3 py-2.5 text-sm font-medium transition-colors ${
                answer?.selected_option_id === opt.id
                  ? "border-primary/60 bg-primary/10 text-primary ring-1 ring-primary/30"
                  : "border-border hover:bg-muted/40"
              }`}
            >
              {getTrueFalseLabel(opt.option_text, t)}
            </button>
          ))}
        </div>
      )}

      {question.question_type === "short_answer" && (
        <div className="ml-9">
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
