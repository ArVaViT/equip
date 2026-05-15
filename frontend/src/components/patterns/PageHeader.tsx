import type { ReactNode } from "react"
import { Link } from "react-router-dom"
import { ChevronLeft } from "lucide-react"
import { cn } from "@/lib/utils"

interface PageHeaderProps {
  title: ReactNode
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
  description,
  cover,
  meta,
  actions,
  backTo,
  backLabel = "Back",
  className,
}: PageHeaderProps) {
  return (
    <header className={cn("mb-6 space-y-4", className)}>
      {backTo && (
        <Link
          to={backTo}
          className="-mx-2 inline-flex min-h-[44px] items-center gap-1 px-2 text-xs text-muted-foreground hover:text-foreground sm:mx-0 sm:min-h-0 sm:px-0"
        >
          <ChevronLeft className="h-3.5 w-3.5" strokeWidth={1.75} />
          {backLabel}
        </Link>
      )}
      {cover && <div className="max-w-4xl">{cover}</div>}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0 flex-1 text-wrap-safe">{title}</div>
        {actions && (
          <div className="flex shrink-0 items-center gap-2">{actions}</div>
        )}
      </div>
      {description && (
        <div className="max-w-3xl text-sm text-muted-foreground text-wrap-safe">
          {description}
        </div>
      )}
      {meta && (
        <div className="flex flex-wrap items-center gap-2 pt-1">{meta}</div>
      )}
    </header>
  )
}
