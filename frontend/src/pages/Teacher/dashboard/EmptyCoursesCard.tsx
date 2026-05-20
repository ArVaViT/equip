import { Plus } from "lucide-react"
import { useTranslation } from "react-i18next"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { WelcomeCard } from "@/components/dashboard/WelcomeCard"

interface Props {
  onCreate: () => void
}

/**
 * First-time empty state for the teacher dashboard. Uses the shared
 * editorial ``<WelcomeCard>`` composition (thin sage rule → eyebrow →
 * serif title → warm paragraph → one CTA) so the first-time moment
 * matches the student dashboard's onboarding voice rather than the
 * older bare ``BookOpen``-centered placeholder. Wrapped in the same
 * dashed ``<Card>`` chrome the section had before so the page rhythm
 * is preserved.
 */
export function EmptyCoursesCard({ onCreate }: Props) {
  const { t } = useTranslation()
  return (
    <Card className="border-dashed">
      <CardContent className="px-4 py-0">
        <WelcomeCard
          eyebrow={t("onboarding.teacher.eyebrow")}
          title={t("onboarding.teacher.title")}
          description={t("onboarding.teacher.body")}
          action={
            <Button onClick={onCreate} size="sm">
              <Plus className="h-4 w-4 mr-1.5" strokeWidth={1.75} />
              {t("onboarding.teacher.primaryCta")}
            </Button>
          }
        />
      </CardContent>
    </Card>
  )
}
