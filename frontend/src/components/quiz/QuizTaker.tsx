import { useState } from "react"
import { useTranslation } from "react-i18next"
import { Button } from "@/components/ui/button"
import PageSpinner from "@/components/ui/PageSpinner"
import { StaggerChildren } from "@/components/motion"
import { coursesService } from "@/services/courses"
import { getErrorDetail } from "@/lib/errorDetail"
import { toast } from "@/lib/toast"
import type { QuizAttempt } from "@/types"
import { Loader2 } from "lucide-react"
import {
  PreviousAttempts,
  QuestionPrompt,
  QuizHeader,
  ResultsView,
  useQuizTaker,
  type AnswerMap,
  type QuizAnswer,
} from "./taker"

interface QuizTakerProps {
  chapterId: string
  /**
   * When rendered from a ``ChapterBlock`` that points at a specific quiz, pass
   * ``block.quiz_id`` so we only surface that quiz. Otherwise the chapter-level
   * fallback is used (``GET /quizzes/chapter/{id}`` returns the first quiz).
   */
  quizId?: string
  // Called after a successful submit regardless of pass/fail so the parent
  // can re-fetch chapter progress. Without this, a passing attempt would
  // complete the chapter on the server but the next chapter in the UI
  // stayed locked until a full page refresh (completedIds was stale).
  onSubmitted?: () => void
}

export default function QuizTaker({ chapterId, quizId, onSubmitted }: QuizTakerProps) {
  const { t } = useTranslation()
  const { loading, fetchError, quiz, attempts, setAttempts } = useQuizTaker({
    chapterId,
    quizId,
  })
  const [answers, setAnswers] = useState<AnswerMap>({})
  const [submitting, setSubmitting] = useState(false)
  const [result, setResult] = useState<QuizAttempt | null>(null)
  const [showResults, setShowResults] = useState(false)

  if (loading) {
    return <PageSpinner variant="section" />
  }
  if (fetchError) {
    return (
      <p className="text-sm text-destructive py-4 text-center">
        {t("quiz.failedLoad")}
      </p>
    )
  }
  if (!quiz || (quiz.questions ?? []).length === 0) return null

  const sortedQuestions = [...(quiz.questions ?? [])].sort(
    (a, b) => a.order_index - b.order_index,
  )
  const maxAttempts = quiz.max_attempts ?? null
  const attemptsUsed = attempts.filter((a) => !!a.completed_at).length
  const attemptsReached = maxAttempts !== null && attemptsUsed >= maxAttempts
  const assessmentTypeKey = quiz.quiz_type === "exam" ? "quiz.exam" : "quiz.quiz"

  const setAnswer = (questionId: string, value: QuizAnswer) => {
    setAnswers((prev) => ({ ...prev, [questionId]: value }))
  }

  const allAnswered = sortedQuestions.every((q) => {
    const a = answers[q.id]
    if (!a) return false
    if (q.question_type === "short_answer" || q.question_type === "essay") {
      const text = a.text_answer?.trim() ?? ""
      if (!text) return false
      // For ``essay`` the teacher can enforce a minimum length; we block
      // submit until that's reached so students don't accidentally submit
      // half-written work and burn an attempt on an exam.
      if (q.question_type === "essay" && q.min_words && q.min_words > 0) {
        const words = text.split(/\s+/).filter(Boolean).length
        if (words < q.min_words) return false
      }
      return true
    }
    return !!a.selected_option_id
  })

  // Mirrors the backend: only MCQ / true-false questions contribute to the
  // auto-graded score. Open-ended answers (``short_answer`` + ``essay``) are
  // scored by the teacher later.
  const autoMaxScore = sortedQuestions
    .filter(
      (q) => q.question_type === "multiple_choice" || q.question_type === "true_false",
    )
    .reduce((sum, q) => sum + q.points, 0)
  const manualMaxScore = sortedQuestions
    .filter((q) => q.question_type === "short_answer" || q.question_type === "essay")
    .reduce((sum, q) => sum + q.points, 0)

  const handleSubmit = async () => {
    if (!allAnswered) return
    setSubmitting(true)
    try {
      const payload = sortedQuestions.map((q) => ({
        question_id: q.id,
        selected_option_id: answers[q.id]?.selected_option_id,
        text_answer: answers[q.id]?.text_answer,
      }))
      const attempt = await coursesService.submitQuiz(quiz.id, payload)
      setResult(attempt)
      setShowResults(true)
      setAttempts((prev) => [attempt, ...prev])
      onSubmitted?.()
    } catch (error: unknown) {
      const detail = getErrorDetail(error)
      toast({
        title:
          detail ||
          (quiz.quiz_type === "exam" ? t("quiz.submitFailedExam") : t("quiz.submitFailedQuiz")),
        variant: "destructive",
      })
    } finally {
      setSubmitting(false)
    }
  }

  const handleTryAgain = () => {
    setShowResults(false)
    setAnswers({})
    setResult(null)
  }

  const answeredCount = sortedQuestions.reduce((count, q) => {
    const a = answers[q.id]
    if (!a) return count
    if (q.question_type === "short_answer" || q.question_type === "essay") {
      return a.text_answer?.trim() ? count + 1 : count
    }
    return a.selected_option_id ? count + 1 : count
  }, 0)
  const answerProgress = sortedQuestions.length
    ? Math.round((answeredCount / sortedQuestions.length) * 100)
    : 0

  return (
    <div className="mt-6 rounded-lg border border-border bg-card">
      <QuizHeader
        quiz={quiz}
        questionCount={sortedQuestions.length}
        autoMaxScore={autoMaxScore}
        manualMaxScore={manualMaxScore}
        maxAttempts={maxAttempts}
        attemptsUsed={attemptsUsed}
      />

      {showResults && result ? (
        <>
          <ResultsView
            result={result}
            quiz={quiz}
            questions={sortedQuestions}
            answers={answers}
          />
          {!attemptsReached && (
            <div className="px-5 pb-5">
              <Button variant="outline" className="w-full" onClick={handleTryAgain}>
                {t("quiz.tryAgain")}
              </Button>
            </div>
          )}
        </>
      ) : (
        <div className="space-y-6 p-5">
          {!attemptsReached && (
            <div className="flex items-center gap-3" aria-hidden>
              <p className="text-xs font-medium uppercase tracking-[0.18em] text-muted-foreground tabular-nums">
                {t("quiz.progressEyebrow", { current: answeredCount, total: sortedQuestions.length })}
              </p>
              <div className="h-1 flex-1 overflow-hidden rounded-full bg-muted">
                <div
                  className="h-full rounded-full bg-primary transition-[width] duration-300 ease-out"
                  style={{ width: `${answerProgress}%` }}
                />
              </div>
            </div>
          )}

          {attemptsReached && (
            <div className="rounded-md border border-border border-l-stripe border-l-warning bg-warning/10 px-3 py-2 text-xs text-foreground">
              {t("quiz.maxAttemptsReached", { type: t(assessmentTypeKey).toLowerCase() })}
            </div>
          )}
          <StaggerChildren className="space-y-6">
            {sortedQuestions.map((question, idx) => (
              <QuestionPrompt
                key={question.id}
                question={question}
                index={idx}
                answer={answers[question.id]}
                onAnswer={(val) => setAnswer(question.id, val)}
              />
            ))}
          </StaggerChildren>

          <Button
            onClick={handleSubmit}
            disabled={!allAnswered || submitting || attemptsReached}
            className={
              !allAnswered || submitting || attemptsReached
                ? "w-full"
                : "w-full bg-cta-glow"
            }
          >
            {submitting ? (
              <>
                <Loader2 className="h-4 w-4 mr-2 animate-spin" strokeWidth={1.75} />
                {t("quiz.submitting")}
              </>
            ) : quiz.quiz_type === "exam" ? (
              t("quiz.submitExam")
            ) : (
              t("quiz.submitQuiz")
            )}
          </Button>
          {!allAnswered && !attemptsReached && (
            <p className="text-center text-xs text-muted-foreground">
              {t("quiz.answerAll")}
            </p>
          )}
        </div>
      )}

      <PreviousAttempts attempts={attempts} autoMaxScore={autoMaxScore} />
    </div>
  )
}
