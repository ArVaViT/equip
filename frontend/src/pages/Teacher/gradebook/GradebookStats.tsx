import { useTranslation } from "react-i18next"
import { Card, CardContent } from "@/components/ui/card"
import { Users, Award, TrendingUp, Calculator } from "lucide-react"
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
        value={String(studentCount)}
        icon={<Users className="h-6 w-6 text-muted-foreground/60" strokeWidth={1.75} aria-hidden />}
      />
      <StatCard
        label={t("gradebook.stats.classAverage")}
        value={`${classAverage.toFixed(1)}%`}
        icon={<TrendingUp className="h-6 w-6 text-muted-foreground/60" strokeWidth={1.75} aria-hidden />}
      />
      <StatCard
        label={t("gradebook.stats.manuallyGraded")}
        value={`${gradedCount}/${studentCount}`}
        icon={<Award className="h-6 w-6 text-muted-foreground/60" strokeWidth={1.75} aria-hidden />}
      />
      <StatCard
        label={t("gradebook.stats.weights")}
        value={`${config.quiz_weight}/${config.assignment_weight}/${config.participation_weight}`}
        valueClassName="text-sm font-medium mt-0.5"
        icon={<Calculator className="h-6 w-6 text-muted-foreground/60" strokeWidth={1.75} aria-hidden />}
      />
    </div>
  )
}

interface StatCardProps {
  label: string
  value: string
  icon: React.ReactNode
  valueClassName?: string
}

function StatCard({ label, value, icon, valueClassName }: StatCardProps) {
  return (
    <Card>
      <CardContent className="pt-5">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-xs text-muted-foreground">{label}</p>
            <p className={valueClassName ?? "text-2xl font-bold mt-0.5"}>{value}</p>
          </div>
          {icon}
        </div>
      </CardContent>
    </Card>
  )
}
