import { Link } from "react-router-dom"
import { LayoutGroup, motion, useReducedMotion } from "motion/react"
import { cn } from "@/lib/utils"
import { EDITORIAL_EASE } from "@/lib/motion"

/**
 * Shared layout-group id so the active-tab underline animates
 * between desktop nav items. The same constant is consumed by the
 * <LayoutGroup> wrapper in HeaderDesktopNav; exporting it keeps the
 * two in sync without a leaky string literal.
 */
export const HEADER_UNDERLINE_LAYOUT_ID = "header-active-underline"

/**
 * Active-route wrapper used by both the desktop nav bar and the
 * mobile sheet. ``variant`` switches the box model — the bar variant
 * inlays a sliding underline (per HEADER_UNDERLINE_LAYOUT_ID); the
 * sheet variant uses a left border + background tint so the same
 * "this is the current page" affordance reads at touch sizes.
 */
export function HeaderNavLink({
  to,
  active,
  children,
  onNavigate,
  variant = "bar",
}: {
  to: string
  active: boolean
  children: React.ReactNode
  onNavigate?: () => void
  variant?: "bar" | "sheet"
}) {
  const prefersReducedMotion = useReducedMotion()
  const isSheet = variant === "sheet"
  return (
    <Link
      to={to}
      onClick={onNavigate}
      className={cn(
        "font-medium transition-colors duration-200 ease-editorial",
        isSheet
          ? "flex min-h-10 w-full items-center border-l-2 border-transparent py-2 pl-[calc(0.75rem-2px)] pr-3 text-sm active:bg-muted/60"
          : "relative flex h-full items-center px-3 text-sm",
        isSheet &&
          (active
            ? "border-brand bg-muted/25 font-medium text-ink"
            : "text-ink hover:border-edge hover:bg-muted/40"),
        !isSheet &&
          (active ? "text-ink" : "text-ink-muted hover:text-ink"),
      )}
    >
      {children}
      {!isSheet &&
        active &&
        (prefersReducedMotion ? (
          <span
            className="pointer-events-none absolute inset-x-3 bottom-0 h-0.5 rounded-sm bg-brand"
            aria-hidden
          />
        ) : (
          <motion.span
            layoutId={HEADER_UNDERLINE_LAYOUT_ID}
            className="pointer-events-none absolute inset-x-3 bottom-0 h-0.5 rounded-sm bg-brand"
            transition={{ duration: 0.32, ease: EDITORIAL_EASE }}
            aria-hidden
          />
        ))}
    </Link>
  )
}

// Re-export ``LayoutGroup`` so consumers can wrap the nav without an
// extra motion/react import.
export { LayoutGroup }
