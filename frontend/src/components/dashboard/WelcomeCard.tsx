import type { ReactNode } from "react"
import { cn } from "@/lib/utils"

interface WelcomeCardProps {
  /** Small all-caps label above the title (sage accent). */
  eyebrow?: string
  /** Serif headline. Can carry a personalised greeting. */
  title: ReactNode
  /** One paragraph of warm prose — keep it short, this is a calm
   *  welcome, not a feature tour. */
  description?: ReactNode
  /** Single primary call-to-action (usually a `<Button>`). One CTA on
   *  purpose: the editorial moment loses its calm the second a row of
   *  three buttons appears. */
  action?: ReactNode
  className?: string
}

/**
 * Editorial welcome surface for first-time / empty states.
 *
 * Composition rule: thin sage rule → eyebrow → serif title → body →
 * one CTA. Centered, generous vertical rhythm, prose-width body.
 *
 * Used for the **student dashboard** before the first enrollment and
 * the **teacher dashboard** before the first course. The card is bare
 * (no border/background) so it can live inside either an existing
 * shell (the dashboard's My-Courses card) or a page container without
 * a second frame.
 */
export function WelcomeCard({ eyebrow, title, description, action, className }: WelcomeCardProps) {
  return (
    <div
      className={cn(
        "animate-fade-in flex flex-col items-center gap-4 px-4 py-10 text-center sm:py-14",
        className,
      )}
    >
      <span className="block h-px w-12 bg-accent/60" aria-hidden />
      {eyebrow && (
        <p className="text-[11px] font-medium uppercase tracking-[0.22em] text-accent">
          {eyebrow}
        </p>
      )}
      <h2 className="max-w-md font-serif text-2xl font-semibold leading-tight tracking-tight text-foreground sm:text-3xl">
        {title}
      </h2>
      {description && (
        <p className="max-w-md text-sm leading-relaxed text-muted-foreground sm:text-base">
          {description}
        </p>
      )}
      {action && <div className="pt-2">{action}</div>}
    </div>
  )
}
