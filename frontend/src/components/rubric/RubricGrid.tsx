import { useTranslation } from "react-i18next"
import { Check } from "lucide-react"
import { cn } from "@/lib/utils"
import type { Rubric, RubricMark } from "@/types"

interface Props {
  rubric: Rubric
  marks: RubricMark[]
  /** Omitted makes the grid read-only — which is how the student sees it. */
  onChoose?: (criterionId: string, levelId: string) => void
  disabled?: boolean
}

/**
 * The marking grid — one component, two audiences.
 *
 * The teacher taps a level; the student reads the same criteria with their own
 * level marked. Deliberately not two components: a student's «summary of your
 * rubric» drifts from the grid the mark actually came from, and the drift is
 * exactly where «почему у меня 70» stops having an answer.
 *
 * Built for a thumb. Levels are buttons at least 44px tall, the whole row is
 * tappable, and nothing here requires typing — a teacher marking thirty essays
 * on a phone on Sunday evening is the case this has to survive, and typing on
 * a phone is why marking gets postponed and then not done.
 */
export function RubricGrid({ rubric, marks, onChoose, disabled = false }: Props) {
  const { t } = useTranslation()
  const chosen = new Map(marks.map((m) => [m.criterion_id, m.level_id]))
  const readOnly = !onChoose

  const earned = marks.reduce((sum, m) => sum + m.points, 0)
  // Out of the rubric's own total, never out of what has been marked so far:
  // a teacher who has done one criterion of four must not see 100%.
  const complete = rubric.criteria.every((c) => chosen.has(c.id))

  return (
    <div className="space-y-3">
      {rubric.criteria.map((criterion) => {
        const chosenLevel = chosen.get(criterion.id)
        return (
          <div key={criterion.id}>
            <p className="text-sm font-medium">{criterion.title}</p>
            {criterion.description && (
              <p className="mt-0.5 text-xs text-ink-muted">{criterion.description}</p>
            )}
            <div className="mt-1.5 flex flex-wrap gap-1.5">
              {criterion.levels.map((level) => {
                const isChosen = chosenLevel === level.id
                return (
                  <button
                    key={level.id}
                    type="button"
                    // A read-only grid renders the same buttons rather than a
                    // different layout, so the student sees the levels they did
                    // not get as well as the one they did. That is the part
                    // that answers «а что нужно было сделать».
                    disabled={readOnly || disabled}
                    aria-pressed={isChosen}
                    onClick={() => onChoose?.(criterion.id, level.id)}
                    title={level.description ?? undefined}
                    className={cn(
                      "min-h-11 flex-1 basis-[8rem] rounded-md border px-2.5 py-2 text-left text-sm transition-colors",
                      isChosen
                        ? "border-brand bg-brand/10 font-medium text-ink"
                        : "border-edge text-ink-muted",
                      !readOnly && !disabled && !isChosen && "hover:border-brand/40 hover:text-ink",
                      readOnly && "cursor-default",
                    )}
                  >
                    <span className="flex items-center gap-1">
                      {isChosen && <Check className="h-3.5 w-3.5 shrink-0 text-brand" strokeWidth={2} aria-hidden />}
                      {level.label}
                    </span>
                    <span className="mt-0.5 block text-xs tabular-nums opacity-70">{level.points}</span>
                  </button>
                )
              })}
            </div>
          </div>
        )
      })}

      <div className="flex items-baseline justify-between border-t border-edge pt-2">
        <span className="text-sm text-ink-muted">
          {complete ? t("rubric.total") : t("rubric.totalSoFar")}
        </span>
        <span className="text-lg font-semibold tabular-nums">
          {earned} / {rubric.max_score}
        </span>
      </div>
      {!complete && !readOnly && (
        // Said plainly rather than left to be inferred from a disabled button:
        // the work stays with the teacher until every row has a decision, and
        // no number reaches the student before then.
        <p className="text-xs text-ink-muted">{t("rubric.incompleteHint")}</p>
      )}
    </div>
  )
}
