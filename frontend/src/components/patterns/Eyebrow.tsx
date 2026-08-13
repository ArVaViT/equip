import type { ElementType, LabelHTMLAttributes } from "react"
import { cn } from "@/lib/utils"

interface EyebrowProps extends LabelHTMLAttributes<HTMLElement> {
  /** Rendered element — `p` by default; use `label` (with `htmlFor`)
   *  or `div` where semantics require it. */
  as?: ElementType
  /**
   * - `muted` (default): the canonical DESIGN.md eyebrow —
   *   `text-xs font-medium uppercase tracking-[0.18em] text-ink-muted`.
   * - `accent`: the celebration/first-run variant with wider tracking
   *   and the academic-gold accent color.
   */
  tone?: "muted" | "accent"
}

/**
 * Editorial eyebrow — the tiny uppercase label that sits above a
 * heading. Encodes the DESIGN.md recipe (11px is the one documented
 * arbitrary-size exception; the wide tracking is load-bearing) so
 * call sites stop drifting between 10px/11px/text-xs re-typings.
 */
export function Eyebrow({ as: Comp = "p", tone = "muted", className, ...props }: EyebrowProps) {
  return (
    <Comp
      className={cn(
        "text-xs font-medium uppercase",
        tone === "muted" && "tracking-[0.18em] text-ink-muted",
        tone === "accent" && "tracking-[0.22em] text-accent",
        className,
      )}
      {...props}
    />
  )
}
