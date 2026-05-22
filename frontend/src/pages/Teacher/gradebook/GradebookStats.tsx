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
        // Composite triple like "30/50/20" would feel chunky at the
        // default ``text-2xl font-bold`` — keep it readable.
        value={`${config.quiz_weight}/${config.assignment_weight}/${config.participation_weight}`}
        valueClassName="text-base font-semibold"
        icon={Calculator}
      />
    </div>
  )
}
