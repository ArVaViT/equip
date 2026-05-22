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
}

export function EmptyState({
  icon,
  title,
  description,
  action,
  className,
  variant = "default",
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
          <span className="text-muted-foreground/80 [&_svg]:h-5 [&_svg]:w-5">
            {icon}
          </span>
        )}
        <p className="text-sm text-muted-foreground">{title}</p>
        {description && (
          <p className="max-w-md text-xs text-muted-foreground/80">
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
        "animate-fade-in flex flex-col items-center justify-center gap-3 rounded-md border border-dashed border-border bg-background px-6 py-12 text-center",
        className,
      )}
    >
      {icon && (
        <span className="flex h-10 w-10 items-center justify-center rounded-full bg-muted text-muted-foreground [&_svg]:h-5 [&_svg]:w-5">
          {icon}
        </span>
      )}
      <div className="space-y-1">
        <p className="font-serif text-base font-semibold text-foreground">{title}</p>
        {description && (
          <p className="max-w-md text-sm text-muted-foreground">{description}</p>
        )}
      </div>
      {action && <div className="pt-1">{action}</div>}
    </div>
  )
}
