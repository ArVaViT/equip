import { cn } from "@/lib/utils"

/**
 * Decorative loading placeholder. Hidden from assistive tech by default —
 * the shape is purely visual, and announcing it would just say "blank
 * blank blank" while the real content streams in. The surrounding region
 * (page, card, etc.) is responsible for its own `aria-busy` if AT users
 * should be told a load is in progress.
 *
 * `aria-hidden` is set on the wrapper, but callers can override via the
 * standard HTML attribute if they want their skeleton announced.
 */
function Skeleton({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      aria-hidden="true"
      className={cn("skeleton-shimmer", className)}
      {...props}
    />
  )
}

export { Skeleton }
