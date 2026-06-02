import type { ReactNode } from "react"
import { AlertTriangle } from "lucide-react"
import { useTranslation } from "react-i18next"
import { cn } from "@/lib/utils"

interface ErrorStateProps {
  /** Icon slot. Defaults to <AlertTriangle strokeWidth={1.75} />. */
  icon?: ReactNode
  /** Short headline. Defaults to a localized "Something went wrong". */
  title?: string
  /** Optional longer explanation or retry hint. */
  description?: string
  /** Primary action — typically a Retry button. */
  action?: ReactNode
  /** Optional secondary action — e.g. "Back" link. */
  secondaryAction?: ReactNode
  className?: string
}

/**
 * Page- or section-level error placeholder.
 *
 * Renders a centered column (icon / title / description / actions) with the
 * destructive color tone applied to the icon. Use whenever data loading
 * fails and we want to show the user a recoverable state instead of an
 * empty page. For "no data yet" cases that are not errors, use {@link EmptyState}.
 */
export function ErrorState({
  icon,
  title,
  description,
  action,
  secondaryAction,
  className,
}: ErrorStateProps) {
  const { t } = useTranslation()
  const resolvedTitle = title ?? t("common.somethingWentWrong")
  return (
    <div
      role="alert"
      className={cn(
        "animate-fade-in flex flex-col items-center justify-center gap-4 py-20 text-center",
        className,
      )}
    >
      <span className="text-destructive/60 [&_svg]:h-12 [&_svg]:w-12 [&_svg]:stroke-[1.75]">
        {icon ?? <AlertTriangle strokeWidth={1.75} aria-hidden />}
      </span>
      <div className="space-y-1">
        <h2 className="font-serif text-base font-semibold tracking-tight text-ink">{resolvedTitle}</h2>
        {description && (
          <p className="max-w-md text-sm text-ink-muted">{description}</p>
        )}
      </div>
      {(action || secondaryAction) && (
        <div className="flex items-center justify-center gap-2">
          {action}
          {secondaryAction}
        </div>
      )}
    </div>
  )
}
