import { useTranslation } from "react-i18next"
import { Award, TrendingUp } from "lucide-react"
import { StatCard } from "@/components/patterns"

interface Props {
  averageProgress: number
  completionRate: number
}

/**
 * Two numbers, side by side on every width. There was a third — the number of
 * students — which the table heading right below already says, and on a phone
 * the three stacked tiles filled the first screen: a teacher looking for their
 * students scrolled past a page of summary before meeting a name.
 */
export function ProgressStats({ averageProgress, completionRate }: Props) {
  const { t } = useTranslation()

  return (
    <div className="mb-6 grid grid-cols-2 gap-3 sm:mb-8 sm:gap-4">
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
