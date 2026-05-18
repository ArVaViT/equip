import { useTranslation } from "react-i18next"
import { Users, BookOpen, GraduationCap, TrendingUp } from "lucide-react"
import { Card, CardContent } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import type { AdminStats } from "./constants"

interface Props {
  stats: AdminStats
  loading: boolean
}

/**
 * Three-card stats row at the top of the admin overview tab.
 *
 * Each card carries:
 * - small framed icon on the left (consistent with the dashboard side-
 *   rail headers so the visual vocabulary is shared)
 * - eyebrow label
 * - the number — Fraunces serif, large + tabular-nums so a trio of
 *   3-digit metrics line up vertically across cards
 * - an optional secondary line for trend / context (e.g. ``+3 this
 *   week`` on the users card)
 *
 * Replaces the previous shared ``StatCard`` here because admin-
 * specific affordances (trend deltas, eyebrow vocabulary) would have
 * leaked into a primitive that other features also depend on.
 */
export function OverviewStats({ stats, loading }: Props) {
  const { t } = useTranslation()

  const cards: ReadonlyArray<{
    key: keyof Pick<AdminStats, "users" | "courses" | "enrollments">
    icon: typeof Users
    label: string
    secondary?: string
  }> = [
    {
      key: "users",
      icon: Users,
      label: t("admin.overview.totalUsers"),
      // Trend line is shown only when there's something to say —
      // ``undefined`` while loading, 0 means literally "no signups this
      // week" which is still worth surfacing.
      secondary:
        stats.usersLast7Days !== undefined
          ? t("admin.overview.usersLast7Days", { count: stats.usersLast7Days })
          : undefined,
    },
    { key: "courses", icon: BookOpen, label: t("admin.overview.totalCourses") },
    {
      key: "enrollments",
      icon: GraduationCap,
      label: t("admin.overview.totalEnrollments"),
    },
  ] as const

  return (
    <div className="mb-8 grid grid-cols-1 gap-4 sm:grid-cols-3">
      {cards.map(({ key, icon: Icon, label, secondary }) => (
        <Card key={key}>
          <CardContent className="flex items-start gap-4 p-5">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md border border-border/80 bg-card">
              <Icon className="h-5 w-5 text-muted-foreground" strokeWidth={1.75} aria-hidden />
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-[11px] font-medium uppercase tracking-[0.18em] text-muted-foreground">
                {label}
              </p>
              {loading ? (
                <Skeleton className="mt-1.5 h-8 w-20" />
              ) : (
                <p className="mt-0.5 font-serif text-3xl font-semibold tabular-nums leading-tight text-foreground">
                  {stats[key].toLocaleString()}
                </p>
              )}
              {secondary && !loading && (
                <p className="mt-1.5 inline-flex items-center gap-1 text-xs text-muted-foreground">
                  <TrendingUp
                    className="h-3 w-3 shrink-0 text-success"
                    strokeWidth={1.75}
                    aria-hidden
                  />
                  {secondary}
                </p>
              )}
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  )
}
