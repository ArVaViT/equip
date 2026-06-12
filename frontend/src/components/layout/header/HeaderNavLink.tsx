import { Link } from "react-router-dom"
import { cn } from "@/lib/utils"

/**
 * Active-route wrapper used by both the desktop nav bar and the
 * mobile sheet. ``variant`` switches the box model — the bar variant
 * inlays a static underline under the active link; the sheet variant
 * uses a left border + background tint so the same "this is the
 * current page" affordance reads at touch sizes.
 *
 * The underline used to slide between tabs via a motion/react
 * ``layoutId`` span, but that single affordance was the only thing
 * keeping framer-motion in the eager shell chunk (~33 KB gzip). The
 * static underline below is the exact markup the reduced-motion
 * branch already rendered — the slide was deliberately sacrificed
 * for the bundle win.
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
      {!isSheet && active && (
        <span
          className="pointer-events-none absolute inset-x-3 bottom-0 h-0.5 rounded-sm bg-brand"
          aria-hidden
        />
      )}
    </Link>
  )
}
