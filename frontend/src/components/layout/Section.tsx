import { cn } from "@/lib/utils"

/**
 * The page shell. One decision — how wide is this page — instead of twenty.
 *
 * Counted before writing this: `pages/` contained **twenty distinct**
 * `container mx-auto …` strings across roughly fifty files. Not twenty
 * considered choices; the same intent spelled several ways —
 * `container mx-auto px-4 py-8 max-w-6xl` seven times and
 * `container mx-auto max-w-6xl px-4 py-6 sm:py-8` twice, which are the same
 * page in two hands. And the widths split almost evenly across `3xl`, `4xl`,
 * `5xl` and `6xl`, which is the tell: thirty-six pages made the same decision
 * independently and landed in four equal piles, meaning nobody was deciding.
 * They were copying whichever neighbour they opened first.
 *
 * So the prop is not a width. It is **what kind of page this is**, and the
 * width follows:
 *
 * - `reading` — one column of prose read start to finish. A chapter, a legal
 *   document, a certificate. 680px is the measure decision 002 settled on: 68
 *   characters per line in Cyrillic at 17px.
 * - `default` — the ordinary page. A form, a detail view, a list of cards.
 * - `wide` — a page whose content is genuinely tabular or multi-column. A
 *   gradebook, an admin dashboard. Reach for this when narrower would force a
 *   horizontal scroll, not because the page feels important.
 *
 * Vertical rhythm comes with it and is not a prop. A page that needs different
 * spacing above and below its content is a page that should be composing
 * `<Section>`s, not overriding one.
 */
const WIDTHS = {
  reading: "max-w-[680px]",
  default: "max-w-5xl",
  wide: "max-w-[1400px]",
} as const

export function Section({
  width = "default",
  as: Tag = "div",
  className,
  children,
  ...props
}: {
  width?: keyof typeof WIDTHS
  /** `main`, `section`, `article` where the landmark matters. */
  as?: "div" | "main" | "section" | "article"
  className?: string
  children: React.ReactNode
} & Omit<React.HTMLAttributes<HTMLElement>, "className" | "children">) {
  return (
    <Tag
      className={cn("mx-auto w-full px-4 py-6 sm:px-6 sm:py-10", WIDTHS[width], className)}
      {...props}
    >
      {children}
    </Tag>
  )
}
