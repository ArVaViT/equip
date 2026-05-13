import { BookOpen, Plus } from "lucide-react"
import { useTranslation } from "react-i18next"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"

interface Props {
  onCreate: () => void
}

export function EmptyCoursesCard({ onCreate }: Props) {
  const { t } = useTranslation()
  return (
    <Card className="border-dashed">
      <CardContent className="flex flex-col items-center justify-center py-16 text-center">
        <BookOpen className="h-12 w-12 text-muted-foreground/50 mb-4" />
        <h3 className="text-lg font-medium mb-1">
          {t("teacherDashboard.empty.title")}
        </h3>
        <p className="text-sm text-muted-foreground mb-4">
          {t("teacherDashboard.empty.description")}
        </p>
        <Button onClick={onCreate} size="sm">
          <Plus className="h-4 w-4 mr-1.5" />
          {t("teacherDashboard.empty.action")}
        </Button>
      </CardContent>
    </Card>
  )
}
