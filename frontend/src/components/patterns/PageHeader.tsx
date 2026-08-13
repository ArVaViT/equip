import type { ReactNode } from "react"
import { Link } from "react-router-dom"
import { ChevronLeft, type LucideIcon } from "lucide-react"
import { cn } from "@/lib/utils"

/**
 * The top of a page: what it is, and what you can do to it.
 *
 * The old version took `title: ReactNode`, which sounds flexible and was the
 * whole problem. Owning the layout but not the type meant every caller had to
 * bring its own `<h1>` and its own classes — so using the component saved
 * nothing and guaranteed nothing, and the numbers say exactly that:
 * **eight files imported it, twenty-three wrote their own header anyway.**
 *
 * And the eight that did use it still disagreed. Three put an icon beside the
 * heading at three sizes; the headings themselves came in
 * `text-xl sm:text-2xl` and `text-2xl sm:text-3xl` on pages of equal weight.
 * There was no shared decision to disagree with.
 *
 * So `title` is a **string** now and this component sets it. One size for a
 * page heading, one icon size, one gap. A page with something genuinely
 * unusual at the top — an inline-editable course name — passes `titleSlot`
 * instead, and that is a named exception rather than the default door.
 */
interface PageHeaderProps {
  /** The page's heading. Rendered as the `<h1>`, in the page-title type. */
  title?: string
  /**
   * For a heading that is a control rather than a label — `InlineEdit` on the
   * course and module editors. Mutually exclusive with `title`.
   */
  titleSlot?: ReactNode
  /** Small label above the heading. Sentence case; the component tracks it. */
  eyebrow?: string
  /** Sits before the heading at the one size icons go beside headings. */
  icon?: LucideIcon
  description?: ReactNode
  cover?: ReactNode
  meta?: ReactNode
  actions?: ReactNode
  backTo?: string
  backLabel?: string
  className?: string
}

export function PageHeader({
  title,
  titleSlot,
  eyebrow,
  icon: Icon,
  description,
  cover,
  meta,
  actions,
  backTo,
  backLabel = "Back",
  className,
}: PageHeaderProps) {
  return (
    <header className={cn("mb-8 space-y-4", className)}>
      {backTo && (
        <Link
          to={backTo}
          className="-mx-2 inline-flex min-h-[44px] items-center gap-1 rounded-md px-2 text-xs text-ink-muted transition-colors duration-fast hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 sm:mx-0 sm:min-h-0 sm:px-0"
        >
          <ChevronLeft className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
          {backLabel}
        </Link>
      )}
      {cover && <div className="max-w-4xl">{cover}</div>}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0 flex-1 text-wrap-safe">
          {eyebrow && (
            <p className="mb-2 text-xs font-medium uppercase tracking-[0.18em] text-ink-muted">
              {eyebrow}
            </p>
          )}
          {titleSlot ??
            (title && (
              <h1 className="flex items-center gap-2.5 font-serif text-2xl font-semibold tracking-tight text-ink sm:text-3xl">
                {Icon && (
                  <Icon className="h-6 w-6 shrink-0 text-ink-muted" strokeWidth={1.75} aria-hidden />
                )}
                {title}
              </h1>
            ))}
        </div>
        {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
      </div>
      {description && (
        <div className="max-w-3xl text-sm leading-relaxed text-ink-muted text-wrap-safe">
          {description}
        </div>
      )}
      {meta && <div className="flex flex-wrap items-center gap-2 pt-1">{meta}</div>}
    </header>
  )
}
