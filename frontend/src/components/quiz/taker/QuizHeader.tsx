import { ClipboardList } from "lucide-react"
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
  const questionsLabel = t("quiz.nQuestions", { count: questionCount })
  const pointsLabel = t("quiz.nPoints", { count: totalMaxScore })

  return (
    <div className="p-5 border-b">
      <div className="flex items-center gap-2 mb-1">
        <ClipboardList className="h-5 w-5 shrink-0 text-muted-foreground" strokeWidth={1.75} />
        <h3 className="min-w-0 flex-1 text-base font-semibold text-wrap-safe">
          {quiz.title}
        </h3>
      </div>
      {quiz.description && (
        <p className="ml-7 text-sm text-muted-foreground text-wrap-safe whitespace-pre-line">
          {quiz.description}
        </p>
      )}
      <div className="flex items-center gap-4 ml-7 mt-2 text-xs text-muted-foreground flex-wrap">
        <span>{questionsLabel}</span>
        <span>
          {pointsLabel}
          {manualMaxScore > 0 && autoMaxScore > 0 && (
            <>
              {" "}
              {t("quiz.pointsBreakdown", { auto: autoMaxScore, manual: manualMaxScore })}
            </>
          )}
        </span>
        <span>{t("quiz.passingShort", { score: quiz.passing_score })}</span>
        {maxAttempts !== null && (
          <span>{t("quiz.attemptsShort", { used: attemptsUsed, max: maxAttempts })}</span>
        )}
      </div>
    </div>
  )
}
