import { useTranslation } from "react-i18next"
import { cn } from "@/lib/utils"

interface RevealPanelProps {
  isCorrect: boolean
  explanation: string | null
}

/**
 * Post-answer verdict + explanation block for a Daily Challenge
 * question — shared by the dashboard card and the archive replay
 * panel so the reveal reads identically in both places.
 */
export function RevealPanel({ isCorrect, explanation }: RevealPanelProps) {
  const { t } = useTranslation()
  return (
    <div className="space-y-1.5 rounded-md bg-muted/20 px-3 py-2.5">
      <p
        className={cn(
          "text-xs font-semibold uppercase tracking-[0.14em]",
          isCorrect ? "text-success" : "text-ink-muted",
        )}
      >
        {isCorrect ? t("dailyChallenge.reveal.correct") : t("dailyChallenge.reveal.wrong")}
      </p>
      {explanation && <p className="text-xs leading-snug text-ink">{explanation}</p>}
    </div>
  )
}
