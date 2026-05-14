import { useTranslation } from "react-i18next"
import { Card, CardContent } from "@/components/ui/card"
import { Award, TrendingUp, Users } from "lucide-react"

interface Props {
  totalStudents: number
  averageProgress: number
  completionRate: number
}

const CARDS = [
  { key: "total", labelKey: "studentProgress.stats.totalStudents", icon: Users },
  { key: "avg", labelKey: "studentProgress.stats.averageProgress", icon: TrendingUp },
  { key: "completion", labelKey: "studentProgress.stats.completionRate", icon: Award },
] as const

export function ProgressStats({ totalStudents, averageProgress, completionRate }: Props) {
  const { t } = useTranslation()
  const values: Record<(typeof CARDS)[number]["key"], string> = {
    total: totalStudents.toString(),
    avg: `${averageProgress}%`,
    completion: `${completionRate}%`,
  }

  return (
    <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-8">
      {CARDS.map(({ key, labelKey, icon: Icon }) => (
        <Card key={key}>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground">{t(labelKey)}</p>
                <p className="text-2xl font-bold mt-1">{values[key]}</p>
              </div>
              <Icon className="h-6 w-6 text-muted-foreground/60" strokeWidth={1.75} aria-hidden />
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  )
}
