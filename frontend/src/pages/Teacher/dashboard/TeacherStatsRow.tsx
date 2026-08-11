import { useTranslation } from "react-i18next"
import { Bell, BookOpen, ClipboardCheck, Eye } from "lucide-react"
import { StatCard } from "@/components/patterns"
import type { Course } from "@/types"

interface Props {
  courses: Course[]
  pendingActions: number
  /** Work waiting to be marked, across this teacher's courses. */
  pendingGrading: number
}

/**
 * At-a-glance stats row for the teacher dashboard — total courses,
 * published count, total modules authored, and items waiting on the
 * teacher. Every number is derived from data the dashboard already
 * fetched (no extra round-trip): before this the dashboard was just a
 * page title followed straight into the course list, which read as
 * empty/sparse even for a teacher with real courses and real students.
 *
 * Reuses the shared ``<StatCard>`` (the same primitive behind
 * ``ProgressStats``, ``TeacherAnalytics``, and the admin overview row)
 * rather than inventing a teacher-specific card.
 */
export function TeacherStatsRow({ courses, pendingActions, pendingGrading }: Props) {
  const { t } = useTranslation()
  const publishedCount = courses.filter((c) => c.status === "published").length

  return (
    <div className="mb-6 grid grid-cols-2 gap-3 sm:mb-8 lg:grid-cols-4">
      <StatCard
        label={t("teacherDashboard.stats.totalCourses")}
        value={courses.length}
        icon={BookOpen}
        variant="icon-leading"
      />
      <StatCard
        label={t("teacherDashboard.stats.published")}
        value={publishedCount}
        icon={Eye}
        variant="icon-leading"
      />
      {/* Replaces the module count, which nobody acts on. This is the number
          that decides whether a teacher opens the app today. */}
      <StatCard
        label={t("teacherDashboard.stats.pendingGrading")}
        value={pendingGrading}
        icon={ClipboardCheck}
        variant="icon-leading"
      />
      <StatCard
        label={t("teacherDashboard.stats.pendingActions")}
        value={pendingActions}
        icon={Bell}
        variant="icon-leading"
      />
    </div>
  )
}
