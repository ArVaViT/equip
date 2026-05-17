import { useTranslation } from "react-i18next"
import { Award, TrendingUp, Users } from "lucide-react"
import { StatCard } from "@/components/patterns"

interface Props {
  totalStudents: number
  averageProgress: number
  completionRate: number
}

export function ProgressStats({ totalStudents, averageProgress, completionRate }: Props) {
  const { t } = useTranslation()

  return (
    <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-8">
      <StatCard
        label={t("studentProgress.stats.totalStudents")}
        value={totalStudents}
        icon={Users}
      />
      <StatCard
        label={t("studentProgress.stats.averageProgress")}
        value={`${averageProgress}%`}
        icon={TrendingUp}
      />
      <StatCard
        label={t("studentProgress.stats.completionRate")}
        value={`${completionRate}%`}
        icon={Award}
      />
    </div>
  )
}
