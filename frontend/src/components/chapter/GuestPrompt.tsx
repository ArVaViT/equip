import { Link, useParams } from "react-router-dom"
import { useTranslation } from "react-i18next"
import { BookOpen, Lock } from "lucide-react"

import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

type Variant = "block" | "finish" | "wall"

/**
 * What a guest sees where a signed-in reader would act: a test, an
 * assignment or a file inside the preview lesson ("block"), the end of it
 * ("finish"), or any other lesson ("wall").
 *
 * Both buttons come back to the course page, not to the lesson: a new
 * account is not yet enrolled, and the course page is where enrolling is.
 */
export function GuestPrompt({ variant, className }: { variant: Variant; className?: string }) {
  const { t } = useTranslation()
  const { courseId } = useParams<{ courseId: string }>()
  const back = { from: courseId ? `/courses/${courseId}` : "/" }
  const Icon = variant === "finish" ? BookOpen : Lock
  // Inside the lesson, one quiet line; the buttons wait at its end.
  if (variant === "block") {
    return (
      <p className={cn("flex items-center gap-2 rounded-md border border-dashed border-edge px-3 py-2.5 text-sm text-ink-muted", className)}>
        <Lock className="h-4 w-4 shrink-0" strokeWidth={1.75} aria-hidden />
        {t("guest.block.title")}
      </p>
    )
  }
  return (
    <div
      className={cn(
        "rounded-card border border-edge bg-muted/30 p-5",
        variant === "wall" && "py-12 text-center",
        className,
      )}
    >
      <div className={cn("flex items-start gap-3", variant === "wall" && "flex-col items-center")}>
        <Icon className={cn("shrink-0 text-ink-muted", variant === "wall" ? "h-8 w-8" : "mt-0.5 h-5 w-5")} strokeWidth={1.75} aria-hidden />
        <div className="min-w-0">
          <p className={cn("font-medium text-ink", variant === "wall" && "font-serif text-xl font-semibold")}>
            {t(`guest.${variant}.title`)}
          </p>
          <p className="mt-1 text-sm text-ink-muted">{t(`guest.${variant}.body`)}</p>
          <div className={cn("mt-4 flex flex-wrap gap-2", variant === "wall" && "justify-center")}>
            <Button asChild size="sm">
              <Link to="/register" state={back}>
                {t("guest.register")}
              </Link>
            </Button>
            <Button asChild size="sm" variant="outline">
              <Link to="/login" state={back}>
                {t("guest.signIn")}
              </Link>
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}
