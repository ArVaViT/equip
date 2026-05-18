import { useCallback, useEffect, useMemo, useState } from "react"
import { Link, useSearchParams } from "react-router-dom"
import { useTranslation } from "react-i18next"
import { ChevronLeft, ChevronRight, GraduationCap, Plus, Search, X } from "lucide-react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { NativeSelect } from "@/components/ui/native-select"
import { Skeleton } from "@/components/ui/skeleton"
import { DateRangePicker } from "@/components/ui/date-range-picker"
import { EmptyState } from "@/components/patterns/EmptyState"
import { cohortsService } from "@/services/cohorts"
import { formatDate } from "@/i18n/format"
import type { Cohort } from "@/types"
import { CreateCohortDialog } from "./CreateCohortDialog"
import { cn } from "@/lib/utils"

const STATUS_BADGE: Record<Cohort["status"], "success" | "info" | "muted"> = {
  upcoming: "info",
  active: "success",
  completed: "muted",
}

const PAGE_SIZE_OPTIONS = [10, 25, 50, 100] as const
type PageSize = (typeof PAGE_SIZE_OPTIONS)[number]
const DEFAULT_PAGE_SIZE: PageSize = 25
const STATUS_VALUES = ["", "upcoming", "active", "completed"] as const

function isPageSize(n: number): n is PageSize {
  return (PAGE_SIZE_OPTIONS as readonly number[]).includes(n)
}

function ymdKey(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`
}

/**
 * Admin cohort list — top-level ``?tab=cohorts`` view.
 *
 * Mirrors the audit-log shape: filters in the card header, sticky-
 * header table with internal scroll, page-size selector + pagination
 * at the bottom. All filter state lives in the URL (``?cs`` status,
 * ``?cq`` query, ``?cf``/``?ct`` start-date range, ``?cp`` page,
 * ``?cps`` page size) so a director can bookmark or share a
 * specific slice ("active cohorts starting in May").
 */
export function CohortsTab() {
  const { t } = useTranslation()
  const [params, setParams] = useSearchParams()
  const [cohorts, setCohorts] = useState<Cohort[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [createOpen, setCreateOpen] = useState(false)

  // URL-state. ``pickOption`` keeps it well-typed and rejects
  // anything that didn't come from our own UI (drop a garbage
  // ``?cs=999`` and we land on the default).
  const rawStatus = params.get("cs") ?? ""
  const statusFilter = (STATUS_VALUES as readonly string[]).includes(rawStatus)
    ? (rawStatus as "" | Cohort["status"])
    : ""
  const search = (params.get("cq") ?? "").slice(0, 100)
  const startFrom = /^\d{4}-\d{2}-\d{2}$/.test(params.get("cf") ?? "")
    ? params.get("cf")!
    : ""
  const startTo = /^\d{4}-\d{2}-\d{2}$/.test(params.get("ct") ?? "")
    ? params.get("ct")!
    : ""
  const rawPage = Number.parseInt(params.get("cp") ?? "1", 10)
  const page = Number.isFinite(rawPage) && rawPage > 0 ? rawPage : 1
  const rawPageSize = Number.parseInt(params.get("cps") ?? "", 10)
  const pageSize: PageSize = isPageSize(rawPageSize) ? rawPageSize : DEFAULT_PAGE_SIZE

  const filtersActive = Boolean(statusFilter || search || startFrom || startTo)

  const updateCohorts = useCallback(
    (patch: Record<string, string | null>, opts: { resetPage?: boolean } = {}) =>
      setParams(
        (prev) => {
          const n = new URLSearchParams(prev)
          for (const [k, v] of Object.entries(patch)) {
            if (v) n.set(k, v)
            else n.delete(k)
          }
          if (opts.resetPage) n.delete("cp")
          return n
        },
        { replace: true },
      ),
    [setParams],
  )

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await cohortsService.listCohorts(statusFilter || undefined)
      setCohorts(data)
    } catch {
      setError(t("admin.cohorts.loadError"))
    } finally {
      setLoading(false)
    }
  }, [statusFilter, t])

  useEffect(() => {
    void load()
  }, [load])

  // Client-side filter + paginate over the per-status fetch. Cohort
  // counts in production stay in the dozens, so we don't need a
  // server-side search/range yet — keeping it client-side avoids two
  // round trips for one keystroke.
  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    return cohorts.filter((c) => {
      if (q && !c.name.toLowerCase().includes(q)) return false
      const startKey = ymdKey(new Date(c.start_date))
      if (startFrom && startKey < startFrom) return false
      if (startTo && startKey > startTo) return false
      return true
    })
  }, [cohorts, search, startFrom, startTo])

  const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize))
  const safePage = Math.min(page, totalPages)
  const pageItems = useMemo(
    () => filtered.slice((safePage - 1) * pageSize, safePage * pageSize),
    [filtered, safePage, pageSize],
  )

  const setStatus = (v: typeof statusFilter) =>
    updateCohorts({ cs: v || null }, { resetPage: true })
  const setSearch = (v: string) => updateCohorts({ cq: v || null }, { resetPage: true })
  const setStartRange = (range: { from: string; to: string }) =>
    updateCohorts({ cf: range.from || null, ct: range.to || null }, { resetPage: true })
  const setPage = (n: number) => updateCohorts({ cp: n <= 1 ? null : String(n) })
  const setPageSize = (n: PageSize) =>
    updateCohorts(
      { cps: n === DEFAULT_PAGE_SIZE ? null : String(n) },
      { resetPage: true },
    )
  const resetFilters = () =>
    updateCohorts({ cs: null, cq: null, cf: null, ct: null, cp: null })

  return (
    <Card>
      <CardHeader className="gap-3 space-y-0 border-b">
        <div className="flex items-center justify-between gap-3">
          <CardTitle className="text-xl">{t("admin.cohorts.title")}</CardTitle>
          <Button size="sm" onClick={() => setCreateOpen(true)} className="h-9 shrink-0">
            <Plus className="mr-1.5 h-4 w-4" strokeWidth={1.75} aria-hidden />
            {t("admin.cohorts.createButton")}
          </Button>
        </div>
        <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-end">
          <div className="space-y-1">
            <label className="text-xs font-medium text-muted-foreground">
              {t("admin.cohorts.filterStatus")}
            </label>
            <NativeSelect
              fieldSize="sm"
              value={statusFilter}
              onChange={(e) => setStatus(e.target.value as typeof statusFilter)}
              className={cn(
                "w-full sm:w-44",
                statusFilter && "border-primary/40 ring-1 ring-primary/40",
              )}
            >
              <option value="">{t("admin.cohorts.allStatuses")}</option>
              <option value="upcoming">{t("admin.cohorts.statusUpcoming")}</option>
              <option value="active">{t("admin.cohorts.statusActive")}</option>
              <option value="completed">{t("admin.cohorts.statusCompleted")}</option>
            </NativeSelect>
          </div>
          <div className="space-y-1">
            <label className="text-xs font-medium text-muted-foreground">
              {t("admin.cohorts.filterStartRange")}
            </label>
            <DateRangePicker
              value={{ from: startFrom, to: startTo }}
              onChange={setStartRange}
              active={Boolean(startFrom || startTo)}
            />
          </div>
          <div className="space-y-1 sm:flex-1">
            <label className="text-xs font-medium text-muted-foreground" htmlFor="cohort-search">
              {t("admin.cohorts.searchLabel")}
            </label>
            <div className="relative">
              <Search
                className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground"
                strokeWidth={1.75}
                aria-hidden
              />
              <Input
                id="cohort-search"
                fieldSize="sm"
                placeholder={t("admin.cohorts.searchPlaceholder")}
                value={search}
                onChange={(e) => setSearch(e.target.value.slice(0, 100))}
                maxLength={100}
                className="pl-9"
              />
            </div>
          </div>
          {filtersActive && (
            <Button
              variant="ghost"
              size="sm"
              onClick={resetFilters}
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
          <CohortsTableSkeleton />
        ) : error ? (
          <div className="px-6 py-10 text-center">
            <p className="text-sm text-destructive">{error}</p>
            <Button size="sm" variant="outline" className="mt-3" onClick={() => void load()}>
              {t("common.tryAgain")}
            </Button>
          </div>
        ) : filtered.length === 0 ? (
          <div className="px-6 py-10">
            <EmptyCohorts hasQuery={filtersActive} onCreate={() => setCreateOpen(true)} />
          </div>
        ) : (
          <CohortsTable items={pageItems} />
        )}

        <div className="flex flex-col items-stretch gap-2 border-t border-border px-5 py-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <label htmlFor="cohort-page-size">{t("admin.audit.pageSizeLabel")}</label>
            <NativeSelect
              id="cohort-page-size"
              fieldSize="sm"
              value={String(pageSize)}
              onChange={(e) => setPageSize(Number(e.target.value) as PageSize)}
              className="w-20"
            >
              {PAGE_SIZE_OPTIONS.map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </NativeSelect>
            <span className="ml-2">
              {t("admin.cohorts.totalShown", { shown: pageItems.length, total: filtered.length })}
            </span>
          </div>
          <div className="flex items-center justify-between gap-3 sm:justify-end">
            <p className="text-xs text-muted-foreground">
              {t("admin.audit.page", { page: safePage, total: totalPages })}
            </p>
            <div className="flex items-center gap-1.5">
              <Button
                variant="outline"
                size="sm"
                disabled={safePage <= 1}
                onClick={() => setPage(safePage - 1)}
                className="h-9 w-9 p-0"
                aria-label={t("admin.audit.prevPageAria")}
              >
                <ChevronLeft className="h-4 w-4" strokeWidth={1.75} aria-hidden />
              </Button>
              <Button
                variant="outline"
                size="sm"
                disabled={safePage >= totalPages}
                onClick={() => setPage(safePage + 1)}
                className="h-9 w-9 p-0"
                aria-label={t("admin.audit.nextPageAria")}
              >
                <ChevronRight className="h-4 w-4" strokeWidth={1.75} aria-hidden />
              </Button>
            </div>
          </div>
        </div>
      </CardContent>

      <CreateCohortDialog
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onCreated={() => {
          setCreateOpen(false)
          void load()
        }}
      />
    </Card>
  )
}

function CohortsTable({ items }: { items: Cohort[] }) {
  const { t } = useTranslation()
  return (
    <>
      {/* Mobile stack — each row is a tappable card. */}
      <div className="space-y-2 px-4 py-3 sm:hidden">
        {items.map((c) => (
          <Link
            key={c.id}
            to={`/admin/cohorts/${c.id}`}
            className="block rounded-md border border-border bg-card p-3 transition-colors hover:border-primary/30 hover:bg-muted/40"
          >
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium text-foreground">{c.name}</p>
                <p className="mt-1 text-xs text-muted-foreground">
                  {formatDate(c.start_date)} &mdash; {formatDate(c.end_date)}
                </p>
              </div>
              <Badge variant={STATUS_BADGE[c.status]} className="shrink-0 capitalize">
                {t(`admin.cohorts.status${capitalize(c.status)}`)}
              </Badge>
            </div>
            <div className="mt-3 flex items-center gap-4 text-xs text-muted-foreground">
              <span>
                {t("admin.cohorts.thCourses")}:{" "}
                <span className="text-foreground">{c.course_ids.length}</span>
              </span>
              <span>
                {t("admin.cohorts.thStudents")}:{" "}
                <span className="text-foreground">
                  {c.student_count}
                  {c.max_students ? ` / ${c.max_students}` : ""}
                </span>
              </span>
            </div>
          </Link>
        ))}
      </div>

      {/* Desktop sticky-header table with internal scroll. */}
      <div className="hidden max-h-[60vh] overflow-y-auto sm:block">
        <table className="w-full text-sm">
          <thead className="sticky top-0 z-10 bg-card">
            <tr className="border-b text-left">
              <th className="px-5 py-3 font-medium text-muted-foreground">{t("admin.cohorts.thName")}</th>
              <th className="px-5 py-3 font-medium text-muted-foreground">{t("admin.cohorts.thStatus")}</th>
              <th className="px-5 py-3 font-medium text-muted-foreground">{t("admin.cohorts.thDates")}</th>
              <th className="px-5 py-3 font-medium text-muted-foreground">{t("admin.cohorts.thCourses")}</th>
              <th className="px-5 py-3 font-medium text-muted-foreground">{t("admin.cohorts.thStudents")}</th>
            </tr>
          </thead>
          <tbody className="divide-y">
            {items.map((c) => (
              <tr key={c.id} className="transition-colors hover:bg-muted/40">
                <td className="px-5 py-3">
                  <Link to={`/admin/cohorts/${c.id}`} className="font-medium hover:text-primary">
                    {c.name}
                  </Link>
                </td>
                <td className="px-5 py-3">
                  <Badge variant={STATUS_BADGE[c.status]} className="capitalize">
                    {t(`admin.cohorts.status${capitalize(c.status)}`)}
                  </Badge>
                </td>
                <td className="px-5 py-3 text-xs text-muted-foreground">
                  {formatDate(c.start_date)} &mdash; {formatDate(c.end_date)}
                </td>
                <td className="px-5 py-3 text-muted-foreground">{c.course_ids.length}</td>
                <td className="px-5 py-3 text-muted-foreground">
                  {c.student_count}
                  {c.max_students ? ` / ${c.max_students}` : ""}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  )
}

function capitalize(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1)
}

function EmptyCohorts({ hasQuery, onCreate }: { hasQuery: boolean; onCreate: () => void }) {
  const { t } = useTranslation()
  return (
    <EmptyState
      variant="compact"
      icon={<GraduationCap strokeWidth={1.75} aria-hidden />}
      title={hasQuery ? t("admin.cohorts.emptyNoMatch") : t("admin.cohorts.emptyNoCohorts")}
      action={
        !hasQuery ? (
          <Button size="sm" onClick={onCreate}>
            <Plus className="mr-1.5 h-4 w-4" strokeWidth={1.75} aria-hidden />
            {t("admin.cohorts.createButton")}
          </Button>
        ) : undefined
      }
    />
  )
}

/** Loading placeholder. Mirrors the table layout so the grid doesn't snap. */
function CohortsTableSkeleton() {
  return (
    <div aria-busy="true">
      <div className="space-y-2 px-4 py-3 sm:hidden">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="rounded-md border border-border bg-card p-3">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0 flex-1 space-y-2">
                <Skeleton className="h-4 w-2/3" />
                <Skeleton className="h-3 w-1/2" />
              </div>
              <Skeleton className="h-5 w-16 rounded-full" />
            </div>
            <div className="mt-3 flex items-center gap-4">
              <Skeleton className="h-3 w-20" />
              <Skeleton className="h-3 w-24" />
            </div>
          </div>
        ))}
      </div>
      <div className="hidden max-h-[60vh] overflow-y-auto sm:block">
        {Array.from({ length: 6 }).map((_, row) => (
          <div key={row} className="flex items-center gap-4 border-b px-5 py-3">
            {Array.from({ length: 5 }).map((_, col) => (
              <Skeleton key={col} className="h-4 flex-1" />
            ))}
          </div>
        ))}
      </div>
    </div>
  )
}
