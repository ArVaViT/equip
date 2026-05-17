import { useTranslation } from "react-i18next"
import { Users, BookOpen, GraduationCap } from "lucide-react"
import { StatCard } from "@/components/patterns"
import type { AdminStats } from "./constants"

interface Props {
  stats: AdminStats
  loading: boolean
}

const CARDS = [
  { key: "users", i18nKey: "admin.overview.totalUsers", icon: Users },
  { key: "courses", i18nKey: "admin.overview.totalCourses", icon: BookOpen },
  { key: "enrollments", i18nKey: "admin.overview.totalEnrollments", icon: GraduationCap },
] as const

/** Three-card stats row on the admin overview tab. */
export function OverviewStats({ stats, loading }: Props) {
  const { t } = useTranslation()
  return (
    <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-8">
      {CARDS.map(({ key, i18nKey, icon }) => (
        <StatCard
          key={key}
          variant="icon-leading"
          icon={icon}
          label={t(i18nKey)}
          value={loading ? "—" : stats[key].toLocaleString()}
        />
      ))}
    </div>
  )
}
