import { Plus } from "lucide-react"
import { useTranslation } from "react-i18next"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { WelcomeCard } from "@/components/dashboard/WelcomeCard"

interface Props {
  onCreate: () => void
  /** Click handler for the secondary "Take a tour" link — opens the
   *  teacher dashboard tour. Optional because the same empty-state is
   *  shown in places (test harnesses, story files) where a tour isn't
   *  wired up. */
  onTourStart?: () => void
}

/**
 * First-time empty state for the teacher dashboard. Uses the shared
 * editorial ``<WelcomeCard>`` composition (thin sage rule → eyebrow →
 * serif title → warm paragraph → primary + optional tour CTA) so the
 * first-time moment matches the student dashboard's onboarding voice
 * rather than the older bare ``BookOpen``-centered placeholder.
 * Wrapped in the same dashed ``<Card>`` chrome the section had before
 * so the page rhythm is preserved.
 */
export function EmptyCoursesCard({ onCreate, onTourStart }: Props) {
  const { t } = useTranslation()
  return (
    <Card className="border-dashed">
      <CardContent className="px-4 py-0">
        <WelcomeCard
          eyebrow={t("onboarding.teacher.eyebrow")}
          title={t("onboarding.teacher.title")}
          description={t("onboarding.teacher.body")}
          action={
            <div className="flex flex-col items-center gap-2 sm:flex-row">
              <Button onClick={onCreate} size="sm">
                <Plus className="h-4 w-4 mr-1.5" strokeWidth={1.75} />
                {t("onboarding.teacher.primaryCta")}
              </Button>
              {onTourStart && (
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  onClick={onTourStart}
                  className="text-muted-foreground hover:text-foreground"
                >
                  {t("tour.takeATour")}
                </Button>
              )}
            </div>
          }
        />
      </CardContent>
    </Card>
  )
}
