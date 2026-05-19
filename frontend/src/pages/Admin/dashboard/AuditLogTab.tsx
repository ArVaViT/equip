import { useTranslation } from "react-i18next"
import { Link } from "react-router-dom"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Skeleton } from "@/components/ui/skeleton"
import { DateRangePicker } from "@/components/ui/date-range-picker"
import { cn } from "@/lib/utils"
import { EmptyState } from "@/components/patterns/EmptyState"
import { FileText, ChevronLeft, ChevronRight, X } from "lucide-react"
import type { AuditLogEntry } from "@/types"
import {
  ACTION_OPTIONS,
  RESOURCE_OPTIONS,
  ACTION_BADGE_VARIANT,
} from "./constants"
import { AUDIT_PAGE_SIZE_OPTIONS, type AuditPageSize } from "./useAdminAudit"
import { AuditDetailsCell } from "./AuditDetailsCell"
import { AuditSummaryRow } from "./AuditSummaryRow"
import { FilterField } from "./FilterField"
import { formatDateTime, formatRelative } from "@/i18n/format"

interface Props {
  logs: AuditLogEntry[]
  total: number
  loading: boolean
  page: number
  pageSize: AuditPageSize
  userMap: Record<string, string>
  action: string
  resource: string
  dateFrom: string
  dateTo: string
  onAction: (next: string) => void
  onResource: (next: string) => void
  /** Single atomic setter for both date bounds — the date-range picker
   *  emits both at once, so writing them through two separate setters
   *  raced and dropped the ``from`` bound. */
  onDateRange: (from: string, to: string) => void
  onReset: () => void
  onPageChange: (nextPage: number) => void
  onPageSizeChange: (next: AuditPageSize) => void
}

/**
 * Full audit-log tab.
 *
 * **Single-viewport contract** on lg+ — the card grows to fill the
 * remaining viewport below the admin chrome (page header + dashboard
 * title + tab strip + container padding). The table body then takes
 * whatever's left after the filter row + footer, so a long page only
 * scrolls the rows themselves, not the surrounding chrome.
 *
 * Chrome budget on desktop (lg+):
 *   - page header           ``h-12``    = 48 px
 *   - container padding    ``sm:py-8``  = 64 px (top+bot)
 *   - admin title + tabs               ≈ 95 px
 *
 * ``-200px`` leaves a small breathing margin. Below ``md`` the
 * filter row can wrap to two lines, eating an extra ~50 px — the
 * ``md`` breakpoint switches to a more conservative budget.
 */
export function AuditLogTab({
  logs,
  total,
  loading,
  page,
  pageSize,
  userMap,
  action,
  resource,
  dateFrom,
  dateTo,
  onAction,
  onResource,
  onDateRange,
  onReset,
  onPageChange,
  onPageSizeChange,
}: Props) {
  const { t } = useTranslation()
  const totalPages = Math.max(1, Math.ceil(total / pageSize))
  const filtersActive = Boolean(action || resource || dateFrom || dateTo)

  return (
    <Card className="flex max-h-[calc(100dvh-240px)] flex-col md:max-h-[calc(100dvh-200px)] md:min-h-[420px]">
      <CardHeader className="shrink-0 gap-3 space-y-0 border-b">
        <CardTitle className="flex items-center gap-2 text-xl">
          <FileText className="h-5 w-5 shrink-0" strokeWidth={1.75} aria-hidden />
          {t("admin.audit.title")}
          <span className="ml-1.5 text-sm font-normal text-muted-foreground">
            {t("admin.audit.entriesCount", { count: total })}
          </span>
        </CardTitle>
        <div className="flex flex-wrap items-end gap-3">
          <FilterField label={t("admin.audit.filterAction")}>
            {({ id }) => (
              <Select
                value={action || "all"}
                onValueChange={(v) => onAction(v === "all" ? "" : v)}
              >
                <SelectTrigger
                  id={id}
                  size="sm"
                  className={cn(
                    "h-9 w-full sm:w-44",
                    action && "border-primary/40 ring-1 ring-primary/40",
                  )}
                >
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">{t("admin.audit.filterAllActions")}</SelectItem>
                  {ACTION_OPTIONS.map((o) => (
                    <SelectItem key={o} value={o}>
                      {t(`admin.audit.actionValue.${o}`)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          </FilterField>
          <FilterField label={t("admin.audit.filterResource")}>
            {({ id }) => (
              <Select
                value={resource || "all"}
                onValueChange={(v) => onResource(v === "all" ? "" : v)}
              >
                <SelectTrigger
                  id={id}
                  size="sm"
                  className={cn(
                    "h-9 w-full sm:w-44",
                    resource && "border-primary/40 ring-1 ring-primary/40",
                  )}
                >
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">{t("admin.audit.filterAllResources")}</SelectItem>
                  {RESOURCE_OPTIONS.map((o) => (
                    <SelectItem key={o} value={o}>
                      {t(`admin.audit.resourceValue.${o}`)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          </FilterField>
          <FilterField label={t("admin.audit.filterRange")}>
            {() => (
              <DateRangePicker
                value={{ from: dateFrom, to: dateTo }}
                onChange={({ from, to }) => onDateRange(from, to)}
                active={Boolean(dateFrom || dateTo)}
              />
            )}
          </FilterField>
          {filtersActive && (
            <Button
              variant="ghost"
              size="sm"
              onClick={onReset}
              className="h-9 self-end text-muted-foreground hover:text-foreground"
            >
              <X className="mr-1 h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
              {t("admin.audit.filterClear")}
            </Button>
          )}
        </div>
      </CardHeader>
      <CardContent className="flex min-h-0 flex-1 flex-col p-0">
        {loading ? (
          <AuditTableSkeleton />
        ) : logs.length === 0 ? (
          <div className="flex flex-1 items-center justify-center px-6 py-10">
            <EmptyState
              variant="compact"
              icon={<FileText strokeWidth={1.75} aria-hidden />}
              title={t("admin.audit.empty")}
            />
          </div>
        ) : (
          <>
            <AuditSummaryRow logs={logs} />
            <AuditTable logs={logs} userMap={userMap} />
          </>
        )}

        <div className="flex shrink-0 flex-col items-stretch gap-2 border-t border-border px-5 py-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <label htmlFor="audit-page-size">{t("admin.audit.pageSizeLabel")}</label>
            <Select
              value={String(pageSize)}
              onValueChange={(v) => onPageSizeChange(Number(v) as AuditPageSize)}
            >
              <SelectTrigger id="audit-page-size" size="sm" className="h-9 w-20">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {AUDIT_PAGE_SIZE_OPTIONS.map((n) => (
                  <SelectItem key={n} value={String(n)}>
                    {n}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="flex items-center justify-between gap-3 sm:justify-end">
            <p className="text-xs text-muted-foreground">
              {t("admin.audit.page", { page, total: totalPages })}
            </p>
            <div className="flex items-center gap-1.5">
              <Button
                variant="outline"
                size="sm"
                disabled={page <= 1}
                onClick={() => onPageChange(page - 1)}
                className="h-9 w-9 p-0"
                aria-label={t("admin.audit.prevPageAria")}
              >
                <ChevronLeft className="h-4 w-4" strokeWidth={1.75} aria-hidden />
              </Button>
              <Button
                variant="outline"
                size="sm"
                disabled={page >= totalPages}
                onClick={() => onPageChange(page + 1)}
                className="h-9 w-9 p-0"
                aria-label={t("admin.audit.nextPageAria")}
              >
                <ChevronRight className="h-4 w-4" strokeWidth={1.75} aria-hidden />
              </Button>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

function AuditTable({
  logs,
  userMap,
}: {
  logs: AuditLogEntry[]
  userMap: Record<string, string>
}) {
  const { t } = useTranslation()
  return (
    // ``flex-1 min-h-0`` so the table area takes whatever's left
    // between the filter row (above) and the pagination (below);
    // ``sticky top-0`` on <thead> keeps column heads visible while
    // the body scrolls.
    <div className="min-h-0 flex-1 overflow-y-auto">
      <table className="w-full text-sm">
        <thead className="sticky top-0 z-10 bg-card">
          <tr className="border-b text-left">
            <th className="px-5 py-3 font-medium text-muted-foreground">{t("admin.audit.thDate")}</th>
            <th className="px-5 py-3 font-medium text-muted-foreground">{t("admin.audit.thUser")}</th>
            <th className="px-5 py-3 font-medium text-muted-foreground">{t("admin.audit.thAction")}</th>
            <th className="px-5 py-3 font-medium text-muted-foreground">{t("admin.audit.thResource")}</th>
            <th className="px-5 py-3 font-medium text-muted-foreground">{t("admin.audit.thDetails")}</th>
            <th className="px-5 py-3 font-medium text-muted-foreground">{t("admin.audit.thIp")}</th>
          </tr>
        </thead>
        <tbody className="divide-y">
          {logs.map((log) => (
            <tr key={log.id} className="align-top transition-colors hover:bg-muted/40">
              <td
                className="whitespace-nowrap px-5 py-3 text-xs text-muted-foreground"
                title={formatDateTime(log.created_at)}
              >
                {formatRelative(log.created_at)}
              </td>
              <td className="max-w-[160px] truncate px-5 py-3 text-xs" title={log.user_id ?? ""}>
                {log.user_id ? userMap[log.user_id] || `${log.user_id.slice(0, 8)}…` : "—"}
              </td>
              <td className="px-5 py-3">
                <Badge variant={ACTION_BADGE_VARIANT[log.action] ?? "muted"}>
                  {t(`admin.audit.actionValue.${log.action}`, { defaultValue: log.action })}
                </Badge>
              </td>
              <td className="px-5 py-3 text-xs">
                <AuditResourceCell type={log.resource_type} id={log.resource_id} />
              </td>
              <td className="max-w-[320px] px-5 py-3">
                <AuditDetailsCell details={log.details} />
              </td>
              <td className="px-5 py-3 text-xs text-muted-foreground">{log.ip_address || "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/**
 * Resource cell — type label on top, id below. When the resource type
 * has a public detail page (currently only ``course`` / ``cohort``),
 * the id becomes a Link so admins can jump straight to the affected
 * entity. Other types render as plain mono text — we don't fabricate
 * links to non-existent routes.
 */
function AuditResourceCell({ type, id }: { type: string; id: string }) {
  const { t } = useTranslation()
  const label = t(`admin.audit.resourceValue.${type}`, { defaultValue: type })
  const shortId = id.length > 14 ? `${id.slice(0, 14)}…` : id
  const href = resourceHref(type, id)
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-muted-foreground">{label}</span>
      {href ? (
        <Link
          to={href}
          className="max-w-[160px] truncate font-mono text-[10px] text-primary hover:underline"
          title={id}
        >
          {shortId}
        </Link>
      ) : (
        <span
          className="max-w-[160px] truncate font-mono text-[10px] text-muted-foreground/70"
          title={id}
        >
          {shortId}
        </span>
      )}
    </div>
  )
}

function resourceHref(type: string, id: string): string | null {
  switch (type) {
    case "course":
      return `/courses/${id}`
    case "cohort":
      return `/admin/cohorts/${id}`
    default:
      return null
  }
}

/**
 * Loading placeholder. Renders 8 ghost rows in the table layout so
 * column widths don't snap when real data arrives.
 */
function AuditTableSkeleton() {
  return (
    <div className="min-h-0 flex-1 overflow-y-auto" aria-busy="true">
      <div className="flex gap-4 border-b px-5 py-3">
        {Array.from({ length: 6 }).map((_, i) => (
          <Skeleton key={i} className="h-3 flex-1" />
        ))}
      </div>
      {Array.from({ length: 8 }).map((_, row) => (
        <div key={row} className="flex items-center gap-4 border-b px-5 py-3">
          {Array.from({ length: 6 }).map((_, col) => (
            <Skeleton key={col} className="h-4 flex-1" />
          ))}
        </div>
      ))}
    </div>
  )
}
