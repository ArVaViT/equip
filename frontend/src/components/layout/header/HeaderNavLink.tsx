import { Link } from "react-router-dom"
import { cn } from "@/lib/utils"

/**
 * Active-route wrapper used by both the desktop bar and the mobile sheet.
 *
 * The bar used to mark the current page with a two-pixel rule underneath it.
 * That affordance is the single most dated thing in the shell — measured
 * against what the references actually do:
 *
 *   - **Vercel** (app chrome, not marketing): items are 14px/400, 36px tall,
 *     6px radius. The current one is a *filled* surface step — `#1f1f1f` on a
 *     black page — and the idle ones are the same size and weight in grey.
 *     The hierarchy is colour and fill. Nothing is underlined, bolder, bigger.
 *   - **Linear**: 13px/400 links in `#8a8f98`, and the one loud element on the
 *     right is a pill.
 *
 * So: a filled pill, and the difference between "here" and "not here" carried
 * by fill plus ink rather than by a rule. It also gives hover somewhere to go
 * — the underline could only appear, whereas a background can arrive at 60%
 * on hover and 100% when you are actually there.
 *
 * Deliberately still no `layoutId` slide. The last one cost 33 KB gzip of
 * framer-motion in the eager shell chunk, and a background transition gets
 * most of the life for nothing. If the slide comes back it comes back behind
 * `LazyMotion`, not by re-importing the whole library into the shell.
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
      aria-current={active ? "page" : undefined}
      onClick={onNavigate}
      className={cn(
        "transition-[color,background-color] duration-fast ease-out",
        isSheet
          ? "flex min-h-11 w-full items-center rounded-lg px-3 py-2 text-sm font-medium"
          : "flex h-9 items-center rounded-lg px-3 text-sm font-medium",
        isSheet &&
          (active
            ? "bg-secondary text-ink"
            : "text-ink-muted hover:bg-secondary/60 hover:text-ink active:bg-secondary"),
        !isSheet &&
          (active
            ? "bg-secondary text-ink"
            : "text-ink-muted hover:bg-secondary/60 hover:text-ink"),
      )}
    >
      {children}
    </Link>
  )
}
