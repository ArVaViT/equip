import { Check, X } from "lucide-react"
import { cn } from "@/lib/utils"
import type { DailyChallengeOption } from "@/services/dailyChallenge"

/**
 * The slice of reveal state the option button needs. Both the dashboard
 * card and the archive detail panel keep richer reveal objects
 * (streak, explanation, …) — structural typing lets them pass those
 * straight through.
 */
export interface OptionRevealView {
  correct_option_id: string
  selected_option_id: string
}

interface OptionButtonProps {
  option: DailyChallengeOption
  reveal: OptionRevealView | null
  disabled: boolean
  onClick: () => void
}

/**
 * One answer option for a Daily Challenge question — the canonical
 * option row shared by the dashboard card and the archive replay panel.
 *
 * States: neutral (pre-answer, hover affordance on row + letter chip),
 * revealed-correct (green), revealed-wrong (red, only on the user's
 * pick), revealed-other (muted).
 */
export function OptionButton({ option, reveal, disabled, onClick }: OptionButtonProps) {
  const isSelected = reveal?.selected_option_id === option.id
  const isCorrect = reveal?.correct_option_id === option.id
  const showAsCorrect = reveal !== null && isCorrect
  const showAsWrong = reveal !== null && isSelected && !isCorrect

  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-pressed={isSelected}
      className={cn(
        "group flex w-full items-center gap-2.5 rounded-md border px-3 py-2 text-left text-xs transition-colors",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40",
        reveal === null && "border-edge bg-surface hover:border-brand/30 hover:bg-muted/30",
        showAsCorrect && "border-success/40 bg-success/10 text-ink",
        showAsWrong && "border-destructive/40 bg-destructive/10 text-ink",
        reveal !== null && !showAsCorrect && !showAsWrong && "border-edge bg-surface text-ink-muted",
        disabled && "cursor-default",
      )}
    >
      <span
        aria-hidden
        className={cn(
          "flex h-5 w-5 shrink-0 items-center justify-center rounded-full border text-xs font-semibold",
          reveal === null && "border-edge text-ink-muted group-hover:border-brand/40",
          showAsCorrect && "border-success bg-success text-success-foreground",
          showAsWrong && "border-destructive bg-destructive text-destructive-foreground",
          reveal !== null && !showAsCorrect && !showAsWrong && "border-edge text-ink-muted",
        )}
      >
        {showAsCorrect ? (
          <Check className="h-3 w-3" strokeWidth={1.75} />
        ) : showAsWrong ? (
          <X className="h-3 w-3" strokeWidth={1.75} />
        ) : (
          String.fromCharCode(65 + option.order_index)
        )}
      </span>
      <span className="min-w-0 flex-1 truncate">{option.option_text}</span>
    </button>
  )
}
