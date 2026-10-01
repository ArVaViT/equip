import { useCallback, useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { useSearchParams } from "react-router-dom"
import { useAsyncData } from "@/hooks/useAsyncData"
import { coursesService } from "@/services/courses"
import type { AuditLogQuery } from "@/services/audit"
import { toast } from "@/lib/toast"
import { getErrorDetail } from "@/lib/errorDetail"
import { zonedWallTimeToUtc } from "@/i18n/timeZone"
import type { AuditLogEntry } from "@/types"
import {
  ACTION_OPTIONS,
  ISO_DATE_REGEX,
  RESOURCE_OPTIONS,
} from "./constants"

export const AUDIT_PAGE_SIZE_OPTIONS = [25, 50, 100] as const
export type AuditPageSize = (typeof AUDIT_PAGE_SIZE_OPTIONS)[number]
const DEFAULT_PAGE_SIZE: AuditPageSize = 25

/*
 * The bounds of a `YYYY-MM-DD` day the admin typed, on the reader's calendar
 * (the profile's zone) — the calendar the table's timestamps are printed in,
 * not the browser's. The parts are passed explicitly: `new Date("2026-05-14")`
 * parses as UTC midnight while `new Date("2026-05-14T23:59:59")` parses as
 * local, and mixing the two clipped late-evening rows. `ISO_DATE_REGEX` has
 * already guaranteed the shape, so the slice indices are stable.
 */
export function dayStartUtc(day: string): Date {
  return zonedWallTimeToUtc(Number(day.slice(0, 4)), Number(day.slice(5, 7)), Number(day.slice(8, 10)))
}

/** The last millisecond of the day: the next midnight less one, since a day is not always 24 hours. */
export function dayEndUtc(day: string): Date {
  const next = new Date(Date.UTC(Number(day.slice(0, 4)), Number(day.slice(5, 7)) - 1, Number(day.slice(8, 10)) + 1))
  const nextStart = zonedWallTimeToUtc(next.getUTCFullYear(), next.getUTCMonth() + 1, next.getUTCDate())
  return new Date(nextStart.getTime() - 1)
}

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
      if (dateFrom) query.date_from = dayStartUtc(dateFrom).toISOString()
      if (dateTo) query.date_to = dayEndUtc(dateTo).toISOString()

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
    // Atomic two-key write. The DateRangePicker fires both bounds in
    // one handler; calling ``setDateFrom`` then ``setDateTo`` back-to-
    // back used to lose the first one — both call ``setSearchParams``,
    // and within a single event the second invocation reads the same
    // ``prev`` URLSearchParams snapshot as the first, so the second
    // write overwrites the first. Folding the two keys into one
    // ``updateAudit`` call is the fix.
    setDateRange: (from: string, to: string) =>
      updateAudit({ af: from || null, at: to || null }, { resetPage: true }),
    setPage: (next: number) => updateAudit({ ap: next <= 1 ? null : String(next) }),
    // Setting page size resets to page 1: the offset that was valid
    // for the old size is meaningless under the new one.
    setPageSize: (next: AuditPageSize) =>
      updateAudit({ aps: next === DEFAULT_PAGE_SIZE ? null : String(next) }, { resetPage: true }),
    resetFilters,
  }
}
