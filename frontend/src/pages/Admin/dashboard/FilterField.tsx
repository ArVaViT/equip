import type { ReactNode } from "react"
import { cn } from "@/lib/utils"

interface Props {
  label: string
  /** Render the actual control. ``htmlFor`` is plumbed through so the
   *  caller can wire the label correctly without re-implementing the
   *  ``<label>`` element. */
  children: (props: { id: string }) => ReactNode
  /** Hide visually but keep for screen readers. Used when a row of
   *  filters has so many siblings that a stack of visible labels
   *  becomes the noisiest part of the page. */
  hideLabel?: boolean
  className?: string
}

let nextId = 0
function genId(): string {
  // Component is small and renders once per filter; a counter id is
  // sufficient and matches existing conventions in this codebase.
  nextId += 1
  return `ff-${nextId}`
}

/**
 * One filter cell — eyebrow-styled label on top, control below.
 *
 * Uses the DESIGN.md eyebrow recipe verbatim (``text-[11px]
 * font-medium uppercase tracking-[0.18em]`` per the
 * ``VerseOfTheDayCard`` / ``StreakCard`` pattern). Shared here so
 * every admin filter — audit log selects, cohorts status, cohort
 * detail student search, date-range pickers — sits at the same
 * baseline with the same label rhythm.
 *
 * Render-prop API instead of a ``htmlFor`` string so a caller can
 * stamp the id once on the label/control pair without the caller
 * having to pick a unique value.
 */
export function FilterField({ label, children, hideLabel = false, className }: Props) {
  const id = genId()
  return (
    <div className={cn("flex flex-col gap-1", className)}>
      <label
        htmlFor={id}
        className={cn(
          "text-[11px] font-medium uppercase tracking-[0.18em] text-muted-foreground",
          hideLabel && "sr-only",
        )}
      >
        {label}
      </label>
      {children({ id })}
    </div>
  )
}
