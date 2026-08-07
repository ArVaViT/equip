import { useTranslation } from "react-i18next"
import { Users, Award, TrendingUp, Calculator } from "lucide-react"
import { StatCard } from "@/components/patterns"
import type { GradingConfig } from "@/types"

interface Props {
  studentCount: number
  classAverage: number
  gradedCount: number
  config: GradingConfig
}

/** Four-card stats row shown at the top of the gradebook. */
export function GradebookStats({ studentCount, classAverage, gradedCount, config }: Props) {
  const { t } = useTranslation()
  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-6">
      <StatCard
        label={t("gradebook.stats.students")}
        value={studentCount}
        icon={Users}
      />
      <StatCard
        label={t("gradebook.stats.classAverage")}
        value={`${classAverage.toFixed(1)}%`}
        icon={TrendingUp}
      />
      <StatCard
        label={t("gradebook.stats.manuallyGraded")}
        value={`${gradedCount}/${studentCount}`}
        icon={Award}
      />
      <StatCard
        label={t("gradebook.stats.weights")}
        // Two categories since D5 — "40/60" reads at a glance.
        value={`${config.quiz_weight}/${config.assignment_weight}`}
        valueClassName="text-base font-semibold"
        icon={Calculator}
      />
    </div>
  )
}
