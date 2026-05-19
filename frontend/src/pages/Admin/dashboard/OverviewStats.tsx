import { useTranslation } from "react-i18next"
import {
  Bell,
  BookOpen,
  GraduationCap,
  TrendingUp,
  Users,
} from "lucide-react"
import { Card, CardContent } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { cn } from "@/lib/utils"
import type { AdminStats } from "./constants"

interface Props {
  stats: AdminStats
  loading: boolean
  /** Count of items currently waiting on the admin (pending-teacher
   *  approvals + teacher-signed-off certs). Drives the 4th \"action
   *  required\" stat card so the admin sees their queue depth at a
   *  glance from anywhere in the overview. Tinted warning when > 0. */
  pendingActions: number
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
interface StatCardConfig {
  key: string
  icon: typeof Users
  label: string
  value: number
  /** Optional secondary line (trend / context). */
  secondary?: string
  /** When ``true``, render the card with warning-tinted chrome — used
   *  by the \"action required\" card so the admin's eye lands on the
   *  queue before the static counters. */
  warningTint?: boolean
  /** When ``true``, use TrendingUp + success-green for the secondary
   *  line. The warning-tint card uses its own framing instead. */
  trending?: boolean
}

export function OverviewStats({ stats, loading, pendingActions }: Props) {
  const { t } = useTranslation()

  const cards: ReadonlyArray<StatCardConfig> = [
    {
      key: "users",
      icon: Users,
      label: t("admin.overview.totalUsers"),
      value: stats.users,
      // Trend line is shown only when there's something to say —
      // ``undefined`` while loading, 0 means literally "no signups this
      // week" which is still worth surfacing.
      secondary:
        stats.usersLast7Days !== undefined
          ? t("admin.overview.usersLast7Days", { count: stats.usersLast7Days })
          : undefined,
      trending: true,
    },
    {
      key: "courses",
      icon: BookOpen,
      label: t("admin.overview.totalCourses"),
      value: stats.courses,
    },
    {
      key: "enrollments",
      icon: GraduationCap,
      label: t("admin.overview.totalEnrollments"),
      value: stats.enrollments,
    },
    {
      key: "pending",
      icon: Bell,
      label: t("admin.overview.pendingActions"),
      value: pendingActions,
      secondary:
        pendingActions === 0
          ? t("admin.overview.pendingClear")
          : t("admin.overview.pendingHint"),
      warningTint: pendingActions > 0,
    },
  ] as const

  return (
    <div className="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
      {cards.map(({ key, icon: Icon, label, value, secondary, warningTint, trending }) => (
        <Card
          key={key}
          className={cn(
            warningTint && "border-l-stripe border-l-warning bg-warning/5",
          )}
        >
          <CardContent className="flex items-start gap-4 p-5">
            <div
              className={cn(
                "flex h-10 w-10 shrink-0 items-center justify-center rounded-md border border-border/80 bg-card",
                warningTint && "border-warning/40 bg-warning/10",
              )}
            >
              <Icon
                className={cn(
                  "h-5 w-5",
                  warningTint ? "text-warning" : "text-muted-foreground",
                )}
                strokeWidth={1.75}
                aria-hidden
              />
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-[11px] font-medium uppercase tracking-[0.18em] text-muted-foreground">
                {label}
              </p>
              {loading ? (
                <Skeleton className="mt-1.5 h-8 w-20" />
              ) : (
                <p
                  className={cn(
                    "mt-0.5 font-serif text-3xl font-semibold tabular-nums leading-tight",
                    warningTint ? "text-warning" : "text-foreground",
                  )}
                >
                  {value.toLocaleString()}
                </p>
              )}
              {secondary && !loading && (
                <p
                  className={cn(
                    "mt-1.5 inline-flex items-center gap-1 text-xs",
                    warningTint ? "text-warning/90" : "text-muted-foreground",
                  )}
                >
                  {trending && (
                    <TrendingUp
                      className="h-3 w-3 shrink-0 text-success"
                      strokeWidth={1.75}
                      aria-hidden
                    />
                  )}
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
