import { useEffect, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { RotateCcw } from "lucide-react"

import { Button } from "@/components/ui/button"
import { useAsyncData } from "@/hooks/useAsyncData"
import { cn } from "@/lib/utils"
import { reviewService, type ReviewVerdict } from "@/services/review"

/**
 * "This week's review" on the course page: a few questions from tests taken
 * a while ago, wrong ones first, one at a time. Practice only — the server
 * writes nothing and no grade moves — so it can be begun and abandoned
 * freely. Absent when there is nothing to review yet.
 */
export function WeeklyReview({ courseId }: { courseId: string }) {
  const { t, i18n } = useTranslation()
  const { data } = useAsyncData(
    async () => {
      try {
        return await reviewService.forCourse(courseId)
      } catch {
        return []
      }
    },
    [courseId, i18n.language],
  )
  const [started, setStarted] = useState(false)
  const [index, setIndex] = useState(0)
  const [verdict, setVerdict] = useState<(ReviewVerdict & { chosen: string }) | null>(null)
  const [right, setRight] = useState(0)
  const [busy, setBusy] = useState(false)
  const [failed, setFailed] = useState(false)
  // Focus follows the reader into each question: the button they pressed
  // ("Start", "Next") is gone the moment they press it.
  const questionRef = useRef<HTMLParagraphElement>(null)
  const resultRef = useRef<HTMLParagraphElement>(null)

  // A new set (another language, another week) starts the review over;
  // keeping the place would pair a verdict with a question not answered.
  useEffect(() => {
    setStarted(false)
    setIndex(0)
    setVerdict(null)
    setRight(0)
    setFailed(false)
  }, [data])

  useEffect(() => {
    if (!started) return
    ;(index < (data?.length ?? 0) ? questionRef : resultRef).current?.focus()
  }, [started, index, data])

  const questions = data ?? []
  if (questions.length === 0) return null
  const done = index >= questions.length
  const question = questions[Math.min(index, questions.length - 1)]!

  const choose = async (optionId: string) => {
    if (verdict || busy) return
    setBusy(true)
    setFailed(false)
    try {
      const v = await reviewService.check(question.id, optionId)
      setVerdict({ ...v, chosen: optionId })
      if (v.correct) setRight((n) => n + 1)
    } catch {
      // A check that failed is not an answer: say so, and let them try again.
      setFailed(true)
    } finally {
      setBusy(false)
    }
  }

  const next = () => {
    setVerdict(null)
    setIndex((i) => i + 1)
  }

  return (
    <section aria-labelledby="weekly-review-heading" className="mt-6 rounded-md border border-edge p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 id="weekly-review-heading" className="flex items-center gap-2 font-serif text-lg font-semibold">
            <RotateCcw className="h-4 w-4 text-ink-muted" strokeWidth={1.75} aria-hidden />
            {t("review.title")}
          </h2>
          <p className="text-xs text-ink-muted">{t("review.hint", { count: questions.length })}</p>
        </div>
        {!started && (
          <Button size="sm" variant="outline" onClick={() => setStarted(true)}>
            {t("review.start")}
          </Button>
        )}
      </div>

      {started && !done && (
        <div className="mt-4 space-y-3">
          <p className="text-xs text-ink-muted">{t("review.progress", { n: index + 1, total: questions.length })}</p>
          <p ref={questionRef} tabIndex={-1} className="font-medium outline-none">
            {question.question_text}
          </p>
          <ul className="space-y-2">
            {question.options.map((o) => {
              const isRight = verdict?.correct_option_id === o.id
              const isChosenWrong = verdict && verdict.chosen === o.id && !verdict.correct
              return (
                <li key={o.id}>
                  <button
                    type="button"
                    onClick={() => void choose(o.id)}
                    disabled={Boolean(verdict) || busy}
                    className={cn(
                      "w-full rounded-md border px-3 py-2 text-left text-sm transition-colors",
                      !verdict && "border-edge hover:bg-muted/40",
                      isRight && "border-success/40 bg-success/10 font-medium text-success-ink",
                      isChosenWrong && "border-destructive/40 bg-destructive/10 text-destructive-ink",
                      verdict && !isRight && !isChosenWrong && "border-edge text-ink-muted",
                    )}
                  >
                    {o.option_text}
                    {isRight && <span className="sr-only"> — {t("quiz.result.rightAnswer")}</span>}
                    {isChosenWrong && <span className="sr-only"> — {t("quiz.result.yourAnswer")}</span>}
                  </button>
                </li>
              )
            })}
          </ul>
          <div className="flex items-center justify-between gap-2" aria-live="polite">
            <p className="text-sm">
              {verdict
                ? verdict.correct
                  ? t("quiz.result.correct")
                  : t("quiz.result.incorrect")
                : failed
                  ? t("review.checkFailed")
                  : ""}
            </p>
            {verdict && (
              <Button size="sm" onClick={next}>
                {index + 1 < questions.length ? t("review.next") : t("review.finish")}
              </Button>
            )}
          </div>
        </div>
      )}

      {started && done && (
        <p ref={resultRef} tabIndex={-1} className="mt-4 text-sm outline-none" aria-live="polite">
          {t("review.result", { right, total: questions.length })}
        </p>
      )}
    </section>
  )
}
