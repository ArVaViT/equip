import type { ReactNode } from "react"
import { cn } from "@/lib/utils"

interface EmptyStateProps {
  icon?: ReactNode
  title: string
  description?: string
  action?: ReactNode
  className?: string
  /**
   * `default` (the editorial dashed-border block) is what most page-level
   * empty states use. `compact` is for nested containers (inside a Card,
   * a Modal, or a small sidebar panel) where a second dashed border would
   * double up and read as heavy — it drops the border/bg and reduces
   * padding so the empty message reads as restrained inline copy.
   */
  variant?: "default" | "compact"
  /**
   * What the title is in the outline. A paragraph by default — most empty
   * states sit under a page heading. When the empty state *is* the page
   * (a sheet not yet closed), pass `"h1"` so the page keeps its one h1;
   * `"h2"` for a section that is otherwise empty. Looks the same either way.
   */
  titleAs?: "p" | "h1" | "h2"
}

export function EmptyState({
  icon,
  title,
  description,
  action,
  className,
  variant = "default",
  titleAs: Title = "p",
}: EmptyStateProps) {
  if (variant === "compact") {
    return (
      <div
        className={cn(
          "animate-fade-in flex flex-col items-center justify-center gap-2 px-4 py-6 text-center",
          className,
        )}
      >
        {icon && (
          <span className="text-ink-muted [&_svg]:h-5 [&_svg]:w-5">
            {icon}
          </span>
        )}
        <Title className="text-sm text-ink-muted">{title}</Title>
        {description && (
          <p className="max-w-md text-xs text-ink-muted">
            {description}
          </p>
        )}
        {action && <div className="pt-1">{action}</div>}
      </div>
    )
  }

  return (
    <div
      className={cn(
        "animate-fade-in flex flex-col items-center justify-center gap-3 rounded-md border border-dashed border-edge bg-surface px-6 py-12 text-center",
        className,
      )}
    >
      {icon && (
        <span className="flex h-10 w-10 items-center justify-center rounded-full bg-muted text-ink-muted [&_svg]:h-5 [&_svg]:w-5">
          {icon}
        </span>
      )}
      <div className="space-y-1">
        <Title className="font-serif text-base font-semibold text-ink">{title}</Title>
        {description && (
          <p className="max-w-md text-sm text-ink-muted">{description}</p>
        )}
      </div>
      {action && <div className="pt-1">{action}</div>}
    </div>
  )
}
