import { useCallback, useEffect, useState } from "react"
import { Link } from "react-router-dom"
import { useTranslation } from "react-i18next"
import { GraduationCap, Plus, Search } from "lucide-react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { NativeSelect } from "@/components/ui/native-select"
import PageSpinner from "@/components/ui/PageSpinner"
import { cohortsService } from "@/services/cohorts"
import { formatDate } from "@/i18n/format"
import type { Cohort } from "@/types"
import { CreateCohortDialog } from "./CreateCohortDialog"

const STATUS_BADGE: Record<Cohort["status"], "success" | "info" | "muted"> = {
  upcoming: "info",
  active: "success",
  completed: "muted",
}

/**
 * Admin cohort list — top-level `?tab=cohorts` view. Lets the director
 * create a new cohort and drill into any existing one. Detail page
 * (`/admin/cohorts/:id`) is a separate route so the URL is shareable.
 */
export function CohortsTab() {
  const { t } = useTranslation()
  const [cohorts, setCohorts] = useState<Cohort[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [search, setSearch] = useState("")
  const [statusFilter, setStatusFilter] = useState<"" | Cohort["status"]>("")
  const [createOpen, setCreateOpen] = useState(false)

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

  const filtered = search
    ? cohorts.filter((c) => c.name.toLowerCase().includes(search.toLowerCase()))
    : cohorts

  return (
    <Card>
      <CardHeader className="flex-col items-stretch gap-3 space-y-0 sm:flex-row sm:flex-wrap sm:items-center sm:justify-between sm:gap-4">
        <CardTitle className="text-xl">{t("admin.cohorts.title")}</CardTitle>
        <div className="flex flex-wrap items-center gap-2 sm:gap-3">
          <NativeSelect
            fieldSize="sm"
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value as typeof statusFilter)}
            className="w-40"
          >
            <option value="">{t("admin.cohorts.allStatuses")}</option>
            <option value="upcoming">{t("admin.cohorts.statusUpcoming")}</option>
            <option value="active">{t("admin.cohorts.statusActive")}</option>
            <option value="completed">{t("admin.cohorts.statusCompleted")}</option>
          </NativeSelect>
          <div className="relative w-full max-w-xs">
            <Search
              className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground"
              strokeWidth={1.75}
              aria-hidden
            />
            <Input
              placeholder={t("admin.cohorts.searchPlaceholder")}
              value={search}
              onChange={(e) => setSearch(e.target.value.slice(0, 100))}
              maxLength={100}
              className="pl-9"
            />
          </div>
          <Button size="sm" onClick={() => setCreateOpen(true)} className="h-11 sm:h-9">
            <Plus className="h-4 w-4 mr-1.5" strokeWidth={1.75} aria-hidden />
            {t("admin.cohorts.createButton")}
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        {loading ? (
          <PageSpinner />
        ) : error ? (
          <div className="py-10 text-center">
            <p className="text-sm text-destructive">{error}</p>
            <Button size="sm" variant="outline" className="mt-3" onClick={() => void load()}>
              {t("common.tryAgain")}
            </Button>
          </div>
        ) : filtered.length === 0 ? (
          <EmptyCohorts hasQuery={Boolean(search)} onCreate={() => setCreateOpen(true)} />
        ) : (
          <>
            {/* Mobile: stack of cards. Each card is the full row, link-wrapped. */}
            <div className="space-y-2 sm:hidden">
              {filtered.map((c) => (
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
                      {t("admin.cohorts.thCourses")}: <span className="text-foreground">{c.course_ids.length}</span>
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

            {/* Desktop: classic table */}
            <div className="hidden overflow-x-auto -mx-6 sm:block">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left">
                    <th className="px-6 py-3 font-medium text-muted-foreground">
                      {t("admin.cohorts.thName")}
                    </th>
                    <th className="px-6 py-3 font-medium text-muted-foreground">
                      {t("admin.cohorts.thStatus")}
                    </th>
                    <th className="px-6 py-3 font-medium text-muted-foreground">
                      {t("admin.cohorts.thDates")}
                    </th>
                    <th className="px-6 py-3 font-medium text-muted-foreground">
                      {t("admin.cohorts.thCourses")}
                    </th>
                    <th className="px-6 py-3 font-medium text-muted-foreground">
                      {t("admin.cohorts.thStudents")}
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {filtered.map((c) => (
                    <tr key={c.id} className="hover:bg-muted/50 transition-colors">
                      <td className="px-6 py-3">
                        <Link
                          to={`/admin/cohorts/${c.id}`}
                          className="font-medium hover:text-primary"
                        >
                          {c.name}
                        </Link>
                      </td>
                      <td className="px-6 py-3">
                        <Badge variant={STATUS_BADGE[c.status]} className="capitalize">
                          {t(`admin.cohorts.status${capitalize(c.status)}`)}
                        </Badge>
                      </td>
                      <td className="px-6 py-3 text-muted-foreground">
                        {formatDate(c.start_date)} &mdash; {formatDate(c.end_date)}
                      </td>
                      <td className="px-6 py-3 text-muted-foreground">
                        {c.course_ids.length}
                      </td>
                      <td className="px-6 py-3 text-muted-foreground">
                        {c.student_count}
                        {c.max_students ? ` / ${c.max_students}` : ""}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
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

function capitalize(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1)
}

function EmptyCohorts({ hasQuery, onCreate }: { hasQuery: boolean; onCreate: () => void }) {
  const { t } = useTranslation()
  return (
    <div className="flex flex-col items-center py-16 text-center">
      <GraduationCap className="h-12 w-12 text-muted-foreground/40 mb-3" strokeWidth={1.5} aria-hidden />
      <p className="text-muted-foreground mb-4">
        {hasQuery ? t("admin.cohorts.emptyNoMatch") : t("admin.cohorts.emptyNoCohorts")}
      </p>
      {!hasQuery && (
        <Button size="sm" onClick={onCreate}>
          <Plus className="h-4 w-4 mr-1.5" strokeWidth={1.75} aria-hidden />
          {t("admin.cohorts.createButton")}
        </Button>
      )}
    </div>
  )
}
