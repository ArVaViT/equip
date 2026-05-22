import { useMemo } from "react"
import { useTranslation } from "react-i18next"
import type { AuditLogEntry } from "@/types"
import { ACTION_BADGE_VARIANT } from "./constants"
import { cn } from "@/lib/utils"

interface Props {
  logs: AuditLogEntry[]
}

/**
 * Compact summary row above the audit table — counts each action
 * appearing on the current page, broken down by action type. Gives
 * the admin a one-glance "what's the shape of recent activity" read
 * before they start scanning rows. Counts are pure derivatives of the
 * already-loaded page, so adding the row doesn't trigger extra API.
 *
 * Intentionally NOT a global "today's stats" — that would need its
 * own endpoint and slow the tab's first paint. Per-page is enough to
 * tell "this is the day's churn" from "this is one user's edit
 * spree" at a glance.
 */
export function AuditSummaryRow({ logs }: Props) {
  const { t } = useTranslation()

  const counts = useMemo(() => {
    const map = new Map<string, number>()
    for (const log of logs) map.set(log.action, (map.get(log.action) ?? 0) + 1)
    return Array.from(map.entries()).sort((a, b) => b[1] - a[1])
  }, [logs])

  if (counts.length === 0) return null

  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 border-b border-border bg-muted/20 px-5 py-2.5 text-xs">
      <span className="font-medium uppercase tracking-[0.18em] text-muted-foreground">
        {t("admin.audit.summaryLabel")}
      </span>
      {counts.map(([action, count]) => {
        const variant = ACTION_BADGE_VARIANT[action] ?? "muted"
        // Map the existing badge variants to a quiet inline pill so
        // the summary row reads as metadata, not as another set of
        // tappable badges competing with the table cells below.
        return (
          <span key={action} className="inline-flex items-center gap-1.5">
            <span className={cn("h-1.5 w-1.5 rounded-full", DOT_TONE[variant])} aria-hidden />
            <span className="font-medium tabular-nums text-foreground">{count}</span>
            <span className="text-muted-foreground">
              {t(`admin.audit.actionValue.${action}`, { defaultValue: action })}
            </span>
          </span>
        )
      })}
    </div>
  )
}

const DOT_TONE: Record<string, string> = {
  successSubtle: "bg-success",
  infoSubtle: "bg-info",
  destructiveSubtle: "bg-destructive",
  primarySubtle: "bg-primary",
  warningSubtle: "bg-warning",
  muted: "bg-muted-foreground/60",
}
