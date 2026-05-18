import { useCallback, useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { useSearchParams } from "react-router-dom"
import { useAsyncData } from "@/hooks/useAsyncData"
import { coursesService } from "@/services/courses"
import type { AuditLogQuery } from "@/services/audit"
import { toast } from "@/lib/toast"
import { getErrorDetail } from "@/lib/errorDetail"
import type { AuditLogEntry } from "@/types"
import {
  ACTION_OPTIONS,
  ISO_DATE_REGEX,
  RESOURCE_OPTIONS,
} from "./constants"

export const AUDIT_PAGE_SIZE_OPTIONS = [25, 50, 100] as const
export type AuditPageSize = (typeof AUDIT_PAGE_SIZE_OPTIONS)[number]
const DEFAULT_PAGE_SIZE: AuditPageSize = 25

function isAuditPageSize(n: number): n is AuditPageSize {
  return (AUDIT_PAGE_SIZE_OPTIONS as readonly number[]).includes(n)
}

interface UseAdminAuditArgs {
  /** When `false` the hook skips fetching — used to avoid loading the
   *  audit log while the user is on another tab. */
  enabled: boolean
}

const pickOption = <T extends readonly string[]>(
  val: string | null,
  opts: T,
): T[number] | "" =>
  val && (opts as readonly string[]).includes(val) ? (val as T[number]) : ""

/**
 * Manages the audit-log tab: URL-driven filter state, paging, and
 * network loading. All filter state is synced to the URL so the tab
 * is bookmarkable and survives navigation.
 */
export function useAdminAudit({ enabled }: UseAdminAuditArgs) {
  const { t } = useTranslation()
  const [params, setParams] = useSearchParams()

  const action = pickOption(params.get("ax"), ACTION_OPTIONS)
  const resource = pickOption(params.get("ar"), RESOURCE_OPTIONS)
  const dateFrom = ISO_DATE_REGEX.test(params.get("af") ?? "") ? params.get("af")! : ""
  const dateTo = ISO_DATE_REGEX.test(params.get("at") ?? "") ? params.get("at")! : ""
  const rawPage = Number.parseInt(params.get("ap") ?? "1", 10)
  const page = Number.isFinite(rawPage) && rawPage > 0 ? rawPage : 1
  // Page size is also URL-state so a bookmarked admin link round-trips.
  // Reject anything not in the allow-list (defaults to 25) so a crafted
  // ``?aps=99999`` can't trigger a backend OOM.
  const rawPageSize = Number.parseInt(params.get("aps") ?? "", 10)
  const pageSize: AuditPageSize = isAuditPageSize(rawPageSize) ? rawPageSize : DEFAULT_PAGE_SIZE

  const [logs, setLogs] = useState<AuditLogEntry[]>([])
  const [total, setTotal] = useState(0)

  const updateAudit = useCallback(
    (patch: Record<string, string | null>, opts: { resetPage?: boolean } = {}) =>
      setParams(
        (prev) => {
          const n = new URLSearchParams(prev)
          for (const [k, v] of Object.entries(patch)) {
            if (v) n.set(k, v)
            else n.delete(k)
          }
          if (opts.resetPage) n.delete("ap")
          return n
        },
        { replace: true },
      ),
    [setParams],
  )

  const { data: fetchedData, loading, error: fetchError } = useAsyncData(
    async (isCancelled) => {
      if (!enabled) return undefined
      const query: AuditLogQuery = { page, page_size: pageSize }
      if (action) query.action = action
      if (resource) query.resource_type = resource
      // Both bounds anchor to the **local** calendar day the admin
      // typed — date_from at 00:00, date_to at 23:59:59. Naive
      // ``new Date("2026-05-14")`` parses as UTC midnight while
      // ``new Date("2026-05-14T23:59:59")`` parses as local, so a
      // round-trip mixed the zones and clipped late-evening events
      // on the user's last day. ``new Date(year, month, day, ...)``
      // is unambiguously local on both ends. ``ISO_DATE_REGEX``
      // already guaranteed the YYYY-MM-DD shape, so the slice
      // indices are stable.
      if (dateFrom) {
        const y = Number(dateFrom.slice(0, 4))
        const m = Number(dateFrom.slice(5, 7))
        const d = Number(dateFrom.slice(8, 10))
        query.date_from = new Date(y, m - 1, d, 0, 0, 0, 0).toISOString()
      }
      if (dateTo) {
        const y = Number(dateTo.slice(0, 4))
        const m = Number(dateTo.slice(5, 7))
        const d = Number(dateTo.slice(8, 10))
        query.date_to = new Date(y, m - 1, d, 23, 59, 59, 999).toISOString()
      }

      const data = await coursesService.getAuditLogs(query)
      if (isCancelled()) return undefined
      return data
    },
    [enabled, page, pageSize, action, resource, dateFrom, dateTo],
  )

  // Sync fetched data into individual state
  useEffect(() => {
    if (!fetchedData) return
    setLogs(fetchedData.items ?? [])
    setTotal(fetchedData.total ?? 0)
  }, [fetchedData])

  // Surface fetch errors as toasts (matching original behaviour)
  useEffect(() => {
    if (!fetchError) return
    const detail = getErrorDetail(fetchError) || t("admin.audit.errorTableMissing")
    toast({ title: `${t("admin.audit.errorPrefix")}: ${detail}`, variant: "destructive" })
  }, [fetchError, t])

  const resetFilters = () =>
    updateAudit({ ax: null, ar: null, af: null, at: null, ap: null })

  return {
    logs,
    total,
    loading,
    page,
    pageSize,
    action,
    resource,
    dateFrom,
    dateTo,
    setAction: (v: string) => updateAudit({ ax: v || null }, { resetPage: true }),
    setResource: (v: string) => updateAudit({ ar: v || null }, { resetPage: true }),
    setDateFrom: (v: string) => updateAudit({ af: v || null }, { resetPage: true }),
    setDateTo: (v: string) => updateAudit({ at: v || null }, { resetPage: true }),
    setPage: (next: number) => updateAudit({ ap: next <= 1 ? null : String(next) }),
    // Setting page size resets to page 1: the offset that was valid
    // for the old size is meaningless under the new one.
    setPageSize: (next: AuditPageSize) =>
      updateAudit({ aps: next === DEFAULT_PAGE_SIZE ? null : String(next) }, { resetPage: true }),
    resetFilters,
  }
}
