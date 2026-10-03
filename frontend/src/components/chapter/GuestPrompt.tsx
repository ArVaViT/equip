import { Link, useLocation, useParams } from "react-router-dom"
import { useTranslation } from "react-i18next"
import { BookOpen, Lock } from "lucide-react"

import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

type Variant = "finish" | "wall" | "enrollFinish" | "enrollWall"

/**
 * Inside the preview lesson, where a test, an assignment or a file would be:
 * one quiet line, no buttons — those wait at the lesson's end. On its own
 * because a block renders in places with no router at all (tests, previews),
 * and the card below reads the location.
 */
export function LockedBlock({ className }: { className?: string }) {
  const { t } = useTranslation()
  return (
    <p className={cn("flex items-center gap-2 rounded-md border border-dashed border-edge px-3 py-2.5 text-sm text-ink-muted", className)}>
      <Lock className="h-4 w-4 shrink-0" strokeWidth={1.75} aria-hidden />
      {t("guest.block.title")}
    </p>
  )
}

/**
 * What a guest sees where a signed-in reader would act: the end of the
 * preview lesson ("finish"), or any other lesson ("wall").
 *
 * Both buttons come back to this very lesson. They used to lead to the course
 * page, on the reasoning that enrolling is there — but a reader who stopped
 * mid-course to create an account had lost their place and had to find the
 * lesson again. The lesson itself asks them to enrol now (the «enroll…»
 * variants), so the course page is a detour. The path is read from the
 * location rather than built from the params, so a module-shaped address
 * comes back as itself (`lib/authRedirect` validates it either way).
 */
export function GuestPrompt({ variant, className }: { variant: Variant; className?: string }) {
  const { t } = useTranslation()
  const { courseId } = useParams<{ courseId: string }>()
  const location = useLocation()
  const back = { from: `${location.pathname}${location.search}` }
  const Icon = variant === "finish" || variant === "enrollFinish" ? BookOpen : Lock
  const enrolling = variant === "enrollFinish" || variant === "enrollWall"
  const wall = variant === "wall" || variant === "enrollWall"
  return (
    <div
      className={cn(
        "rounded-card border border-edge bg-muted/30 p-5",
        wall && "py-12 text-center",
        className,
      )}
    >
      <div className={cn("flex items-start gap-3", wall && "flex-col items-center")}>
        <Icon className={cn("shrink-0 text-ink-muted", wall ? "h-8 w-8" : "mt-0.5 h-5 w-5")} strokeWidth={1.75} aria-hidden />
        <div className="min-w-0">
          <p className={cn("font-medium text-ink", wall && "font-serif text-xl font-semibold")}>
            {t(`guest.${variant}.title`)}
          </p>
          <p className="mt-1 text-sm text-ink-muted">{t(`guest.${variant}.body`)}</p>
          <div className={cn("mt-4 flex flex-wrap gap-2", wall && "justify-center")}>
            {enrolling ? (
              // Signed in already: what is missing is the enrolment, and the
              // course page is where it happens.
              <Button asChild size="sm">
                <Link to={courseId ? `/courses/${courseId}` : "/"}>{t("guest.toCourse")}</Link>
              </Button>
            ) : (
              <>
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
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
