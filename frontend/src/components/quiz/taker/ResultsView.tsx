import { AlertCircle, BookOpen, CheckCircle, Trophy, XCircle } from "lucide-react"
import { useTranslation } from "react-i18next"
import { motion, useReducedMotion } from "motion/react"
import { Card, CardContent } from "@/components/ui/card"
import { StaggerChildren } from "@/components/motion"
import type { Quiz, QuizAttempt, QuizQuestion } from "@/types"
import type { AnswerMap } from "./types"
import { getTrueFalseLabel } from "@/components/quiz/editor/types"

interface Props {
  result: QuizAttempt
  quiz: Quiz
  questions: QuizQuestion[]
  answers: AnswerMap
}

export function ResultsView({ result, quiz, questions, answers }: Props) {
  const { t } = useTranslation()
  const prefersReducedMotion = useReducedMotion()
  const scorePercent = result.max_score
    ? Math.round(((result.score ?? 0) / result.max_score) * 100)
    : 0

  const answerMap = new Map((result.answers ?? []).map((a) => [a.question_id, a]))
  const hasOpenEnded = questions.some(
    (q) => q.question_type === "short_answer" || q.question_type === "essay",
  )

  const ResultIcon = result.passed ? Trophy : AlertCircle
  const iconColor = result.passed ? "text-success" : "text-destructive"

  return (
    <div className="p-5 space-y-6">
      <Card
        className={
          result.passed
            ? "border-l-stripe border-l-success"
            : "border-l-stripe border-l-destructive"
        }
      >
        <CardContent className="py-7 text-center">
          {prefersReducedMotion ? (
            <ResultIcon className={`mx-auto mb-3 h-10 w-10 ${iconColor}`} strokeWidth={1.75} aria-hidden />
          ) : (
            <motion.div
              className="mx-auto mb-3 w-fit"
              initial={{ scale: 0, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              transition={{ type: "spring", stiffness: 320, damping: 18, delay: 0.05 }}
            >
              <ResultIcon className={`h-10 w-10 ${iconColor}`} strokeWidth={1.75} aria-hidden />
            </motion.div>
          )}
          <p className={`mb-2 text-xs font-medium uppercase tracking-[0.18em] ${result.passed ? "text-success" : "text-destructive"}`}>
            {result.passed ? t("quiz.passedTitle") : t("quiz.notPassedTitle")}
          </p>
          <p className="font-serif text-3xl font-semibold tabular-nums tracking-tight">
            {result.score ?? 0}
            <span className="text-muted-foreground/60"> / {result.max_score ?? 0}</span>
          </p>
          <p className="mt-2 text-sm text-muted-foreground tabular-nums">
            {t("quiz.passingScoreLine", { percent: scorePercent, passing: quiz.passing_score })}
          </p>
          {hasOpenEnded && (
            <p className="mt-3 inline-flex items-center gap-1.5 rounded-md border border-warning/30 bg-warning/10 px-2.5 py-1 text-xs font-medium text-warning">
              {t("quiz.pendingTeacherReview")}
            </p>
          )}
        </CardContent>
      </Card>

      <div className="space-y-4">
        <h4 className="text-xs font-medium uppercase tracking-[0.18em] text-muted-foreground">
          {t("quiz.reviewAnswers")}
        </h4>
        <StaggerChildren className="space-y-4">
          {questions.map((q, idx) => {
          const userAnswer = answers[q.id]
          const answerResult = answerMap.get(q.id)
          const isManual =
            q.question_type === "short_answer" || q.question_type === "essay"
          // For manual questions we only flash ✓/✗ once the teacher has
          // actually touched the row (non-zero points or an attached
          // comment). Otherwise the card stays neutral — "pending review".
          const hasGrade =
            isManual &&
            !!answerResult &&
            (answerResult.points_earned > 0 || !!answerResult.grader_comment)
          const isCorrect = isManual
            ? hasGrade
              ? (answerResult?.is_correct ?? null)
              : null
            : (answerResult?.is_correct ?? null)

          return (
            <div
              key={q.id}
              className={`rounded-md border p-3 ${
                isCorrect === null
                  ? "border-border"
                  : isCorrect
                    ? "border-success/30 bg-success/5"
                    : "border-destructive/30 bg-destructive/5"
              }`}
            >
              <div className="flex items-start gap-3 mb-2">
                <span
                  aria-hidden
                  className="inline-flex h-5 min-w-[1.25rem] shrink-0 items-center justify-center rounded border border-border bg-background px-1 text-xs font-medium tabular-nums text-muted-foreground"
                >
                  {idx + 1}
                </span>
                <p className="min-w-0 flex-1 text-sm font-medium leading-relaxed text-wrap-safe whitespace-pre-line">
                  {q.question_text}
                </p>
                {isCorrect !== null && (
                  <span className="shrink-0">
                    {isCorrect ? (
                      <CheckCircle className="h-4 w-4 text-success" strokeWidth={1.75} />
                    ) : (
                      <XCircle className="h-4 w-4 text-destructive" strokeWidth={1.75} />
                    )}
                  </span>
                )}
              </div>
              {!isManual && (
                <div className="ml-7 space-y-1">
                  {[...(q.options ?? [])]
                    .sort((a, b) => a.order_index - b.order_index)
                    .map((opt) => {
                      const isSelected = userAnswer?.selected_option_id === opt.id
                      const isRight = answerResult?.correct_option_id === opt.id
                      const displayText =
                        q.question_type === "true_false"
                          ? getTrueFalseLabel(opt.option_text, t)
                          : opt.option_text
                      return (
                        <div
                          key={opt.id}
                          className={`rounded px-2 py-1 text-xs ${
                            isRight
                              ? "bg-success/15 font-medium text-success"
                              : isSelected
                                ? "bg-destructive/15 text-destructive"
                                : "text-muted-foreground"
                          }`}
                        >
                          {isSelected && !isRight ? "✗ " : ""}
                          {isRight ? "✓ " : ""}
                          {displayText}
                        </div>
                      )
                    })}
                </div>
              )}
              {isManual && (
                <div className="ml-7 space-y-1.5">
                  {hasGrade ? (
                    <div className="flex flex-wrap items-center gap-2 text-xs">
                      <span className="inline-flex items-center gap-1 rounded-md border border-success/30 bg-success/10 px-2 py-1 font-medium text-success">
                        <CheckCircle className="h-3.5 w-3.5" strokeWidth={1.75} />
                        {t("quiz.gradedPoints", {
                          count: q.points,
                          earned: answerResult?.points_earned ?? 0,
                          max: q.points,
                        })}
                      </span>
                      {answerResult?.grader_comment && (
                        <span className="text-muted-foreground">
                          “{answerResult.grader_comment}”
                        </span>
                      )}
                    </div>
                  ) : (
                    <div className="flex w-fit items-center gap-1.5 rounded-md border border-warning/30 bg-warning/10 px-2.5 py-1.5 text-xs font-medium text-warning">
                      <BookOpen className="h-3.5 w-3.5 shrink-0" strokeWidth={1.75} />
                      {t("quiz.sentForReview")}
                    </div>
                  )}
                  {userAnswer?.text_answer && (
                    <p className="text-xs text-muted-foreground italic whitespace-pre-wrap">
                      {t("quiz.yourAnswer")} {userAnswer.text_answer}
                    </p>
                  )}
                </div>
              )}
            </div>
          )
        })}
        </StaggerChildren>
      </div>
    </div>
  )
}
