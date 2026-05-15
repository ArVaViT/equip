import { GraduationCap, HelpCircle } from "lucide-react"
import { useTranslation } from "react-i18next"
import type { Quiz } from "@/types"

interface Props {
  quiz: Quiz
  questionCount: number
  autoMaxScore: number
  manualMaxScore: number
  maxAttempts: number | null
  attemptsUsed: number
}

export function QuizHeader({
  quiz,
  questionCount,
  autoMaxScore,
  manualMaxScore,
  maxAttempts,
  attemptsUsed,
}: Props) {
  const { t } = useTranslation()
  const totalMaxScore = autoMaxScore + manualMaxScore
  const isExam = quiz.quiz_type === "exam"
  const TypeIcon = isExam ? GraduationCap : HelpCircle
  const typeLabel = isExam ? t("quiz.exam") : t("quiz.quiz")
  const questionsLabel = t("quiz.nQuestions", { count: questionCount })
  const pointsLabel = t("quiz.nPoints", { count: totalMaxScore })

  return (
    <div className="border-b border-border px-5 py-5">
      <p className="mb-2 flex items-center gap-1.5 text-xs font-medium uppercase tracking-[0.18em] text-muted-foreground">
        <TypeIcon className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
        {typeLabel}
      </p>
      <h3 className="font-serif text-lg font-semibold tracking-tight text-wrap-safe">
        {quiz.title}
      </h3>
      {quiz.description && (
        <p className="mt-1.5 text-sm leading-relaxed text-muted-foreground text-wrap-safe whitespace-pre-line">
          {quiz.description}
        </p>
      )}
      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
        <span className="tabular-nums">{questionsLabel}</span>
        <span aria-hidden className="text-muted-foreground/40">·</span>
        <span className="tabular-nums">
          {pointsLabel}
          {manualMaxScore > 0 && autoMaxScore > 0 && (
            <>
              {" "}
              {t("quiz.pointsBreakdown", { auto: autoMaxScore, manual: manualMaxScore })}
            </>
          )}
        </span>
        <span aria-hidden className="text-muted-foreground/40">·</span>
        <span className="tabular-nums">{t("quiz.passingShort", { score: quiz.passing_score })}</span>
        {maxAttempts !== null && (
          <>
            <span aria-hidden className="text-muted-foreground/40">·</span>
            <span className="tabular-nums">{t("quiz.attemptsShort", { used: attemptsUsed, max: maxAttempts })}</span>
          </>
        )}
      </div>
    </div>
  )
}
