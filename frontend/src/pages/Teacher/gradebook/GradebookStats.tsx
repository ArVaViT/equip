import { useTranslation } from "react-i18next"
import { Users, Award, TrendingUp, Calculator } from "lucide-react"
import { StatCard } from "@/components/patterns"
import { formatPercent } from "@/i18n/number"
import type { GradingConfig } from "@/types"

interface Props {
  studentCount: number
  classAverage: number | null
  /** «40/60» actually applied, or null when nothing has been calculated. */
  effectiveWeights?: string | null
  gradedCount: number
  config: GradingConfig
}

/** Four-card stats row shown at the top of the gradebook. */
export function GradebookStats({ studentCount, classAverage, gradedCount, config, effectiveWeights }: Props) {
  const configured = `${config.quiz_weight}/${config.assignment_weight}`
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
        value={classAverage === null ? "—" : formatPercent(classAverage, 1)}
        icon={TrendingUp}
      />
      <StatCard
        label={t("gradebook.stats.manuallyGraded")}
        value={`${gradedCount}/${studentCount}`}
        icon={Award}
      />
      <StatCard
        label={t("gradebook.stats.weights")}
        // The split the grades were actually computed from, not the one on the
        // settings page — showing the configured 40/60 next to scores computed
        // as 100/0 is how a gradebook loses a teacher's trust. Falls back to
        // the configured pair when there is no calculated row to read from.
        value={effectiveWeights ?? `${config.quiz_weight}/${config.assignment_weight}`}
        // When the two differ, the card sits directly above a settings panel
        // showing the other pair. Two numbers contradicting each other with no
        // word between them is how a teacher concludes the app is broken.
        hint={
          effectiveWeights && effectiveWeights !== configured
            ? t("gradebook.stats.weightsDiffer", { configured })
            : undefined
        }
        valueClassName="text-base font-semibold"
        icon={Calculator}
      />
    </div>
  )
}
