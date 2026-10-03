import { useState } from "react"
import { Link, useLocation, useNavigate, useParams } from "react-router-dom"
import { useTranslation } from "react-i18next"
import { BookOpen, Lock } from "lucide-react"

import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import { toast } from "@/lib/toast"
import { coursesService } from "@/services/courses"
import { planEnrollment } from "@/pages/Course/detail/enrollPlan"
import type { Cohort, Course } from "@/types"

type Variant = "finish" | "wall" | "enrollFinish" | "enrollWall"

/**
 * What a signed-in reader may do about enrolling without leaving the lesson.
 *
 * `then` is where to go once enrolled: the lesson they were refused (from
 * the wall) or the one after this (from the end of the preview).
 * `onEnrolled` lets the page forget it was previewing before the step.
 */
export interface EnrollOffer {
  course: Course
  cohorts: Cohort[]
  then: string
  onEnrolled: () => void
}

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
 * «Записаться на курс» for a reader who is signed in but not enrolled.
 *
 * It was a link to the course page, where enrolling is — and the course
 * page, once there, offered the same button and then sent the reader back
 * to find the lesson again. One press enrols here and steps on, with the
 * same call and the same two toasts the course page uses. The course page
 * keeps the cases a button cannot settle: a choice between cohorts, a course
 * by invitation, a closed window — each has a sentence or a dialog there.
 */
function EnrollButton({ offer, courseHref }: { offer?: EnrollOffer; courseHref: string }) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [enrolling, setEnrolling] = useState(false)
  const plan = offer ? planEnrollment(offer.course, offer.cohorts) : null
  if (!offer || !plan || plan.kind !== "enroll") {
    return (
      <Button asChild size="sm">
        <Link to={courseHref}>{t("guest.toCourse")}</Link>
      </Button>
    )
  }
  const enroll = async () => {
    setEnrolling(true)
    try {
      await coursesService.enrollInCourse(offer.course.id, plan.cohortId)
      offer.onEnrolled()
      toast({ title: t("toast.enrolledSuccess"), variant: "success" })
      navigate(offer.then)
    } catch {
      toast({ title: t("toast.enrolledFailed"), variant: "destructive" })
    } finally {
      setEnrolling(false)
    }
  }
  return (
    <Button size="sm" disabled={enrolling} onClick={() => void enroll()}>
      {enrolling ? t("courseDetail.enrolling") : t("guest.toCourse")}
    </Button>
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
export function GuestPrompt({
  variant,
  className,
  offer,
}: {
  variant: Variant
  className?: string
  /** For the «enroll…» variants: what enrolling here would do. Without it, the course page. */
  offer?: EnrollOffer
}) {
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
              <EnrollButton offer={offer} courseHref={courseId ? `/courses/${courseId}` : "/"} />
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
