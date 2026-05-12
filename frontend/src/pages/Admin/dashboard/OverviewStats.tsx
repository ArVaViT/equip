import { useTranslation } from "react-i18next"
import { Card, CardContent } from "@/components/ui/card"
import { Users, BookOpen, GraduationCap } from "lucide-react"
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
      {CARDS.map(({ key, i18nKey, icon: Icon }) => (
        <Card key={key}>
          <CardContent className="flex items-center gap-4 p-5">
            <div className="rounded-md bg-muted p-3">
              <Icon className="h-6 w-6 text-muted-foreground" strokeWidth={1.75} aria-hidden />
            </div>
            <div>
              <p className="text-sm text-muted-foreground">{t(i18nKey)}</p>
              <p className="text-2xl font-bold">
                {loading ? "—" : stats[key].toLocaleString()}
              </p>
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  )
}
