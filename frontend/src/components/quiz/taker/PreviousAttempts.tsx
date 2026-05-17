import { CheckCircle, Clock, XCircle } from "lucide-react"
import { useTranslation } from "react-i18next"
import type { QuizAttempt } from "@/types"
import { formatDate } from "@/i18n/format"

interface Props {
  attempts: QuizAttempt[]
  autoMaxScore: number
}

export function PreviousAttempts({ attempts, autoMaxScore }: Props) {
  const { t } = useTranslation()
  if (attempts.length === 0) return null
  return (
    <div className="border-t p-5">
      <h4 className="text-sm font-medium mb-3 flex items-center gap-2">
        <Clock className="h-4 w-4 text-muted-foreground" strokeWidth={1.75} />
        {t("quiz.previousAttempts")}
      </h4>
      <div className="space-y-2">
        {attempts.map((att) => {
          const inProgress = !att.completed_at
          const style = inProgress
            ? "bg-muted/30 border border-border"
            : att.passed
              ? "border border-success/30 bg-success/10"
              : "border border-destructive/30 bg-destructive/10"
          return (
            <div
              key={att.id}
              className={`flex items-center justify-between px-3 py-2 rounded-md text-sm ${style}`}
            >
              <div className="flex items-center gap-2">
                {inProgress ? (
                  <Clock className="h-4 w-4 text-muted-foreground" strokeWidth={1.75} />
                ) : att.passed ? (
                  <CheckCircle className="h-4 w-4 text-success" strokeWidth={1.75} />
                ) : (
                  <XCircle className="h-4 w-4 text-destructive" strokeWidth={1.75} />
                )}
                <span>
                  {t("quiz.attemptPoints", {
                    score: att.score ?? 0,
                    max: att.max_score ?? autoMaxScore,
                  })}
                </span>
              </div>
              <span className="text-xs text-muted-foreground">
                {att.completed_at ? formatDate(att.completed_at) : t("quiz.inProgress")}
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}
