import { useTranslation } from "react-i18next"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { NativeSelect } from "@/components/ui/native-select"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Skeleton } from "@/components/ui/skeleton"
import { FileText, ChevronLeft, ChevronRight } from "lucide-react"
import type { AuditLogEntry } from "@/types"
import {
  ACTION_OPTIONS,
  RESOURCE_OPTIONS,
  ACTION_BADGE_VARIANT,
} from "./constants"
import { formatDateTime } from "@/i18n/format"

interface Props {
  logs: AuditLogEntry[]
  total: number
  loading: boolean
  page: number
  pageSize: number
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
}

/** Full audit-log tab: filters, table, and pagination. */
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
}: Props) {
  const { t } = useTranslation()
  const totalPages = Math.max(1, Math.ceil(total / pageSize))

  return (
    <div className="space-y-6">
      <Card>
        <CardContent className="p-4">
          <div className="grid grid-cols-1 gap-3 sm:flex sm:flex-wrap sm:items-end">
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
            <FilterDate label={t("admin.audit.filterFrom")} value={dateFrom} onChange={onDateFrom} />
            <FilterDate label={t("admin.audit.filterTo")} value={dateTo} onChange={onDateTo} />
            <Button variant="ghost" size="sm" onClick={onReset} className="h-11 sm:h-9">
              {t("admin.audit.filterClear")}
            </Button>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-xl flex items-center gap-2">
            <FileText className="h-5 w-5 shrink-0" strokeWidth={1.75} aria-hidden />
            {t("admin.audit.title")}
            <span className="text-sm font-normal text-muted-foreground ml-2">
              {t("admin.audit.entriesCount", { count: total })}
            </span>
          </CardTitle>
        </CardHeader>
        <CardContent>
          {loading ? (
            <AuditTableSkeleton />
          ) : logs.length === 0 ? (
            <div className="flex flex-col items-center py-16 text-center">
              <FileText className="mb-3 h-12 w-12 text-muted-foreground/40" strokeWidth={1.75} aria-hidden />
              <p className="text-muted-foreground">{t("admin.audit.empty")}</p>
            </div>
          ) : (
            <>
              <AuditTable logs={logs} userMap={userMap} />
              <div className="flex items-center justify-between px-5 pb-1 pt-4">
                <p className="text-xs text-muted-foreground">
                  {t("admin.audit.page", { page, total: totalPages })}
                </p>
                <div className="flex items-center gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={page <= 1}
                    onClick={() => onPageChange(page - 1)}
                    className="h-11 w-11 p-0 sm:h-9 sm:w-9"
                    aria-label={t("admin.audit.prevPageAria", { defaultValue: "Previous page" })}
                  >
                    <ChevronLeft className="h-4 w-4" strokeWidth={1.75} aria-hidden />
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={page >= totalPages}
                    onClick={() => onPageChange(page + 1)}
                    className="h-11 w-11 p-0 sm:h-9 sm:w-9"
                    aria-label={t("admin.audit.nextPageAria", { defaultValue: "Next page" })}
                  >
                    <ChevronRight className="h-4 w-4" strokeWidth={1.75} aria-hidden />
                  </Button>
                </div>
              </div>
            </>
          )}
        </CardContent>
      </Card>
    </div>
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
  return (
    <div className="space-y-1">
      <label className="text-xs font-medium text-muted-foreground">{label}</label>
      <NativeSelect
        fieldSize="md"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full sm:w-auto"
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

function FilterDate({
  label,
  value,
  onChange,
}: {
  label: string
  value: string
  onChange: (next: string) => void
}) {
  return (
    <div className="space-y-1">
      <label className="text-xs font-medium text-muted-foreground">{label}</label>
      <Input
        type="date"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        fieldSize="md"
        className="w-full sm:w-40"
      />
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
    <div className="overflow-x-auto -mx-6">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b text-left">
            <th className="px-6 py-3 font-medium text-muted-foreground">{t("admin.audit.thDate")}</th>
            <th className="px-6 py-3 font-medium text-muted-foreground">{t("admin.audit.thUser")}</th>
            <th className="px-6 py-3 font-medium text-muted-foreground">{t("admin.audit.thAction")}</th>
            <th className="px-6 py-3 font-medium text-muted-foreground">{t("admin.audit.thResource")}</th>
            <th className="px-6 py-3 font-medium text-muted-foreground">{t("admin.audit.thResourceId")}</th>
            <th className="px-6 py-3 font-medium text-muted-foreground">{t("admin.audit.thIp")}</th>
          </tr>
        </thead>
        <tbody className="divide-y">
          {logs.map((log) => (
            <tr key={log.id} className="hover:bg-muted/50 transition-colors">
              <td className="px-6 py-3 text-muted-foreground whitespace-nowrap">
                {formatDateTime(log.created_at)}
              </td>
              <td className="px-6 py-3 max-w-[160px] truncate" title={log.user_id ?? ""}>
                {log.user_id
                  ? userMap[log.user_id] || log.user_id.slice(0, 8) + "…"
                  : "—"}
              </td>
              <td className="px-6 py-3">
                <Badge variant={ACTION_BADGE_VARIANT[log.action] ?? "muted"}>
                  {t(`admin.audit.actionValue.${log.action}`, {
                    defaultValue: log.action,
                  })}
                </Badge>
              </td>
              <td className="px-6 py-3 text-muted-foreground">
                {t(`admin.audit.resourceValue.${log.resource_type}`, { defaultValue: log.resource_type })}
              </td>
              <td
                className="px-6 py-3 font-mono text-xs text-muted-foreground max-w-[120px] truncate"
                title={log.resource_id}
              >
                {log.resource_id.length > 12
                  ? log.resource_id.slice(0, 12) + "…"
                  : log.resource_id}
              </td>
              <td className="px-6 py-3 text-muted-foreground text-xs">
                {log.ip_address || "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/**
 * Audit-table loading placeholder. Renders 8 ghost rows in the table layout
 * so column widths don't snap when real data arrives. Calling 8 because that's
 * the default page size for the audit log.
 */
function AuditTableSkeleton() {
  return (
    <div className="-mx-6 overflow-x-auto" aria-busy="true">
      <div className="px-6 py-3 border-b flex gap-4">
        {Array.from({ length: 5 }).map((_, i) => (
          <Skeleton key={i} className="h-3 flex-1" />
        ))}
      </div>
      {Array.from({ length: 8 }).map((_, row) => (
        <div key={row} className="px-6 py-3 border-b flex gap-4 items-center">
          {Array.from({ length: 5 }).map((_, col) => (
            <Skeleton key={col} className="h-4 flex-1" />
          ))}
        </div>
      ))}
    </div>
  )
}
