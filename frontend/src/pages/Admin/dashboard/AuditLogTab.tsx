import { useTranslation } from "react-i18next"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { NativeSelect } from "@/components/ui/native-select"
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
import { formatDateTime } from "@/i18n/format"

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
  onDateFrom: (next: string) => void
  onDateTo: (next: string) => void
  onReset: () => void
  onPageChange: (nextPage: number) => void
  onPageSizeChange: (next: AuditPageSize) => void
}

/**
 * Full audit-log tab: filter bar, scrollable table with sticky
 * header, pagination + page-size selector. Filters live in the card
 * header so the bar reads as part of the table view (not as a
 * floating widget). The table body uses internal overflow so a long
 * page doesn't push the rest of the admin UI off-screen.
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
  onDateFrom,
  onDateTo,
  onReset,
  onPageChange,
  onPageSizeChange,
}: Props) {
  const { t } = useTranslation()
  const totalPages = Math.max(1, Math.ceil(total / pageSize))
  const filtersActive = Boolean(action || resource || dateFrom || dateTo)

  return (
    <Card>
      <CardHeader className="gap-3 space-y-0 border-b">
        <CardTitle className="flex items-center gap-2 text-xl">
          <FileText className="h-5 w-5 shrink-0" strokeWidth={1.75} aria-hidden />
          {t("admin.audit.title")}
          <span className="ml-1.5 text-sm font-normal text-muted-foreground">
            {t("admin.audit.entriesCount", { count: total })}
          </span>
        </CardTitle>
        {/* Filter row. Selects sit on the left, the range picker on the
            right of the same row on sm+; on mobile everything stacks
            full-width so the touch targets stay tappable. */}
        <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-end">
          <FilterSelect
            label={t("admin.audit.filterAction")}
            value={action}
            onChange={onAction}
            options={ACTION_OPTIONS}
            optionLabel={(o) => t(`admin.audit.actionValue.${o}`)}
            placeholder={t("admin.audit.filterAllActions")}
          />
          <FilterSelect
            label={t("admin.audit.filterResource")}
            value={resource}
            onChange={onResource}
            options={RESOURCE_OPTIONS}
            optionLabel={(o) => t(`admin.audit.resourceValue.${o}`)}
            placeholder={t("admin.audit.filterAllResources")}
          />
          <div className="space-y-1">
            <label className="text-xs font-medium text-muted-foreground">
              {t("admin.audit.filterRange")}
            </label>
            <DateRangePicker
              value={{ from: dateFrom, to: dateTo }}
              onChange={({ from, to }) => {
                onDateFrom(from)
                onDateTo(to)
              }}
              active={Boolean(dateFrom || dateTo)}
            />
          </div>
          {filtersActive && (
            <Button
              variant="ghost"
              size="sm"
              onClick={onReset}
              className="h-9 self-start text-muted-foreground hover:text-foreground sm:self-end"
            >
              <X className="mr-1 h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
              {t("admin.audit.filterClear")}
            </Button>
          )}
        </div>
      </CardHeader>
      <CardContent className="p-0">
        {loading ? (
          <AuditTableSkeleton />
        ) : logs.length === 0 ? (
          <div className="px-6 py-10">
            <EmptyState
              variant="compact"
              icon={<FileText strokeWidth={1.75} aria-hidden />}
              title={t("admin.audit.empty")}
            />
          </div>
        ) : (
          <AuditTable logs={logs} userMap={userMap} />
        )}

        {/* Pagination + page-size selector. Always shown so the admin
            can dial the density up/down even on an empty filter set. */}
        <div className="flex flex-col items-stretch gap-2 border-t border-border px-5 py-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <label htmlFor="audit-page-size">{t("admin.audit.pageSizeLabel")}</label>
            <NativeSelect
              id="audit-page-size"
              fieldSize="sm"
              value={String(pageSize)}
              onChange={(e) => onPageSizeChange(Number(e.target.value) as AuditPageSize)}
              className="w-20"
            >
              {AUDIT_PAGE_SIZE_OPTIONS.map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </NativeSelect>
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

interface FilterSelectProps {
  label: string
  value: string
  onChange: (next: string) => void
  options: readonly string[]
  optionLabel: (option: string) => string
  placeholder: string
}

function FilterSelect({ label, value, onChange, options, optionLabel, placeholder }: FilterSelectProps) {
  const isActive = value !== ""
  return (
    <div className="space-y-1">
      <label className="text-xs font-medium text-muted-foreground">{label}</label>
      <NativeSelect
        fieldSize="sm"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className={cn(
          "w-full sm:w-44",
          isActive && "border-primary/40 ring-1 ring-primary/40",
        )}
      >
        <option value="">{placeholder}</option>
        {options.map((o) => (
          <option key={o} value={o}>
            {optionLabel(o)}
          </option>
        ))}
      </NativeSelect>
    </div>
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
    // Internal scroll: ``max-h`` is sized so up to ~12 rows show
    // before the body becomes scrollable on a typical viewport.
    // ``sticky top-0`` on <thead> keeps the column heads visible while
    // the body scrolls; the bg fill is required so rows don't bleed
    // through the sticky cells.
    <div className="max-h-[60vh] overflow-y-auto">
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
              <td className="whitespace-nowrap px-5 py-3 text-xs text-muted-foreground">
                {formatDateTime(log.created_at)}
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
                <div className="flex flex-col gap-0.5">
                  <span className="text-muted-foreground">
                    {t(`admin.audit.resourceValue.${log.resource_type}`, {
                      defaultValue: log.resource_type,
                    })}
                  </span>
                  <span
                    className="max-w-[160px] truncate font-mono text-[10px] text-muted-foreground/70"
                    title={log.resource_id}
                  >
                    {log.resource_id.length > 14
                      ? `${log.resource_id.slice(0, 14)}…`
                      : log.resource_id}
                  </span>
                </div>
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
 * Audit-table loading placeholder. Renders 8 ghost rows in the table
 * layout so column widths don't snap when real data arrives.
 */
function AuditTableSkeleton() {
  return (
    <div className="max-h-[60vh] overflow-y-auto" aria-busy="true">
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
