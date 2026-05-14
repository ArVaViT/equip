import { useCallback, useEffect, useState } from "react"
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

const AUDIT_PAGE_SIZE = 25

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
  const [params, setParams] = useSearchParams()

  const action = pickOption(params.get("ax"), ACTION_OPTIONS)
  const resource = pickOption(params.get("ar"), RESOURCE_OPTIONS)
  const dateFrom = ISO_DATE_REGEX.test(params.get("af") ?? "") ? params.get("af")! : ""
  const dateTo = ISO_DATE_REGEX.test(params.get("at") ?? "") ? params.get("at")! : ""
  const rawPage = Number.parseInt(params.get("ap") ?? "1", 10)
  const page = Number.isFinite(rawPage) && rawPage > 0 ? rawPage : 1

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
      const query: AuditLogQuery = { page, page_size: AUDIT_PAGE_SIZE }
      if (action) query.action = action
      if (resource) query.resource_type = resource
      if (dateFrom) query.date_from = new Date(dateFrom).toISOString()
      if (dateTo) query.date_to = new Date(dateTo + "T23:59:59").toISOString()

      const data = await coursesService.getAuditLogs(query)
      if (isCancelled()) return undefined
      return data
    },
    [enabled, page, action, resource, dateFrom, dateTo],
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
    const detail =
      getErrorDetail(fetchError) ||
      "The audit_logs table may not exist yet. Deploy the latest migration."
    toast({ title: `Audit log error: ${detail}`, variant: "destructive" })
  }, [fetchError])

  const resetFilters = () =>
    updateAudit({ ax: null, ar: null, af: null, at: null, ap: null })

  return {
    logs,
    total,
    loading,
    page,
    pageSize: AUDIT_PAGE_SIZE,
    action,
    resource,
    dateFrom,
    dateTo,
    setAction: (v: string) => updateAudit({ ax: v || null }, { resetPage: true }),
    setResource: (v: string) => updateAudit({ ar: v || null }, { resetPage: true }),
    setDateFrom: (v: string) => updateAudit({ af: v || null }, { resetPage: true }),
    setDateTo: (v: string) => updateAudit({ at: v || null }, { resetPage: true }),
    setPage: (next: number) => updateAudit({ ap: next <= 1 ? null : String(next) }),
    resetFilters,
  }
}
