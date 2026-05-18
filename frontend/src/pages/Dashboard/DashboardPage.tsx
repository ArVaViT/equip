import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { Link } from "react-router-dom"
import { motion, useReducedMotion } from "motion/react"
import { Button } from "@/components/ui/button"
import { coursesService } from "@/services/courses"
import type { Enrollment, StudentGrade } from "@/types"
import { useAuth } from "@/context/useAuth"
import { ArrowRight, BookOpen, CheckCircle } from "lucide-react"
import { EmptyState, ErrorState } from "@/components/patterns"
import { Skeleton } from "@/components/ui/skeleton"
import { VerseOfTheDayCard } from "@/components/home/VerseOfTheDayCard"
import { StreakCard } from "@/components/dashboard/StreakCard"
import { cn } from "@/lib/utils"

const EDITORIAL_EASE = [0.22, 1, 0.36, 1] as const

function MyCoursesSection() {
  const { t, i18n } = useTranslation()
  const { user } = useAuth()
  const prefersReducedMotion = useReducedMotion()
  const [enrollments, setEnrollments] = useState<Enrollment[]>([])
  const [grades, setGrades] = useState<StudentGrade[]>([])
  const [loading, setLoading] = useState(true)
  const [fetchError, setFetchError] = useState(false)
  const [retryCount, setRetryCount] = useState(0)

  // ``i18n.language`` in the dep list re-fetches the enrolled-courses
  // payload whenever the user flips locale, so the localised course
  // titles update without a hard page reload. The api interceptor
  // already sends ``Accept-Language`` per request and bakes the locale
  // into the dedupe key (see services/api.ts), so this triggers a real
  // round-trip rather than a cached response.
  useEffect(() => {
    let cancelled = false
    const load = async () => {
      setLoading(true)
      setFetchError(false)
      try {
        const [enrollData, gradeData] = await Promise.all([
          coursesService.getMyCourses(),
          coursesService.getMyGrades().catch(() => []),
        ])
        if (cancelled) return
        setEnrollments(enrollData)
        setGrades(gradeData)
      } catch {
        if (!cancelled) setFetchError(true)
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [user?.id, retryCount, i18n.language])

  const filtered = enrollments.filter((e) => e.course?.created_by !== user?.id)

  const shell = (body: React.ReactNode) => (
    <section className="animate-fade-in overflow-hidden rounded-md border border-border bg-card transition-[border-color] duration-300 hover:border-primary/25">
      <div className="border-b border-border bg-gradient-accent-subtle px-5 py-6 sm:px-8">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:gap-6">
          <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-md border border-border/80 bg-card shadow-none">
            <BookOpen className="h-6 w-6 text-muted-foreground" strokeWidth={1.75} aria-hidden />
          </div>
          <div className="min-w-0 flex-1">
            <h2 className="font-serif text-xl font-semibold tracking-tight text-foreground sm:text-2xl">
              {t("dashboard.myCourses")}
            </h2>
            <p className="mt-1.5 max-w-2xl text-sm leading-relaxed text-muted-foreground">
              {t("dashboard.myCoursesLead")}
            </p>
          </div>
          <Link
            to="/courses"
            className="inline-flex shrink-0 items-center gap-1.5 self-start text-sm font-medium text-primary transition-opacity hover:opacity-80 sm:self-center"
          >
            {t("dashboard.browseAllCta")}
            <ArrowRight className="h-4 w-4" strokeWidth={1.75} aria-hidden />
          </Link>
        </div>
      </div>
      <div className="px-5 py-5 sm:px-8 sm:py-6">{body}</div>
    </section>
  )

  if (loading) {
    return shell(
      <div className="space-y-0 divide-y divide-border/80">
        {Array.from({ length: 2 }).map((_, i) => (
          <div key={i} className="py-5 first:pt-0">
            <Skeleton className="h-5 w-48 max-w-full" />
            <Skeleton className="mt-4 h-1.5 max-w-xs rounded-full" />
          </div>
        ))}
      </div>,
    )
  }

  if (fetchError) {
    return shell(
      <ErrorState
        className="py-10"
        title={t("dashboard.loadCoursesError")}
        action={
          <Button type="button" variant="outline" size="sm" onClick={() => setRetryCount((c) => c + 1)}>
            {t("common.tryAgain")}
          </Button>
        }
      />,
    )
  }

  if (filtered.length === 0) {
    return shell(
      <EmptyState
        className="border-none bg-transparent px-4 py-8 sm:py-10"
        icon={<BookOpen className="text-muted-foreground" strokeWidth={1.75} />}
        title={t("dashboard.myCoursesEmptyTitle")}
        description={t("dashboard.noEnrollments")}
        action={
          <Link to="/courses">
            <Button size="sm">{t("dashboard.browseAllCta")}</Button>
          </Link>
        }
      />,
    )
  }

  return shell(
    <div className="stagger-fade-in flex flex-col gap-4">
      {filtered
        .filter((e) => e.course?.id)
        .map((enrollment, index) => {
          const grade = grades.find((g) => g.course_id === enrollment.course_id)
          const progressColor = enrollment.progress >= 100 ? "bg-success" : "bg-primary"
          const courseId = enrollment.course!.id

          return (
            <Link
              key={enrollment.id}
              to={`/courses/${courseId}`}
              style={{ "--stagger-index": index } as React.CSSProperties}
              className="motion-safe-hover-lift group block rounded-md border border-border/90 bg-muted/10 px-4 py-4 transition-colors hover:border-primary/30 hover:bg-muted/25 sm:px-5"
            >
              <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between sm:gap-6">
                <div className="min-w-0 flex-1 space-y-3">
                  <div className="flex items-start gap-2">
                    <h3 className="min-w-0 flex-1 font-serif text-base font-medium leading-snug text-foreground transition-colors duration-200 group-hover:text-primary">
                      {enrollment.course?.title || t("dashboard.course")}
                    </h3>
                    {enrollment.progress >= 100 && (
                      <CheckCircle className="mt-0.5 h-4 w-4 shrink-0 text-success" strokeWidth={1.75} aria-hidden />
                    )}
                  </div>
                  <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
                    <div className="flex min-w-0 flex-1 items-center gap-3 sm:max-w-md">
                      <div className="h-2 min-w-28 flex-1 overflow-hidden rounded-full bg-muted">
                        {prefersReducedMotion ? (
                          <div
                            className={cn("h-full rounded-full", progressColor)}
                            style={{ width: `${Math.min(enrollment.progress, 100)}%` }}
                          />
                        ) : (
                          <motion.div
                            className={cn("h-full rounded-full", progressColor)}
                            initial={{ width: 0 }}
                            animate={{ width: `${Math.min(enrollment.progress, 100)}%` }}
                            transition={{
                              duration: 0.9,
                              delay: 0.15 + index * 0.045,
                              ease: EDITORIAL_EASE,
                            }}
                          />
                        )}
                      </div>
                      <span className="shrink-0 text-xs font-medium tabular-nums text-muted-foreground">
                        {enrollment.progress}%
                      </span>
                    </div>
                    {grade?.grade ? (
                      <span className="rounded-md border border-border bg-background/80 px-2 py-0.5 text-xs font-medium text-foreground">
                        {t("dashboard.grade", { grade: grade.grade })}
                      </span>
                    ) : null}
                  </div>
                </div>
                <span className="inline-flex shrink-0 items-center text-xs font-medium text-primary sm:flex-col sm:items-end">
                  <span className="flex items-center gap-1.5">
                    {enrollment.progress >= 100 ? t("common.view") : t("common.continue")}
                    <ArrowRight
                      className="h-4 w-4 transition-transform duration-200 group-hover:translate-x-1"
                      strokeWidth={1.75}
                      aria-hidden
                    />
                  </span>
                </span>
              </div>
            </Link>
          )
        })}
    </div>,
  )
}

/**
 * Authenticated landing page. Built as a dashboard, not a catalog —
 * the catalog moved to ``/courses``. The wide left column carries the
 * day-to-day surfaces (My Courses, Streak placeholder), the narrow
 * right column carries the daily Verse of the Day.
 *
 * For unauthenticated visitors the router still sends ``/`` here, but
 * the dashboard sections all check ``user`` and render only when
 * signed in — non-authed visitors see a small "sign in" prompt that
 * sends them to the catalog or the login screen.
 */
export default function DashboardPage() {
  const { t } = useTranslation()
  const { user } = useAuth()

  if (!user) {
    // Guests have no "my courses" / "verse for you" — bounce them to the
    // catalog where they can browse before signing in.
    return (
      <div className="container mx-auto max-w-2xl px-4 py-12 text-center sm:py-20">
        <h1 className="font-serif text-3xl font-bold tracking-tight text-foreground sm:text-4xl">
          {t("common.appName")}
        </h1>
        <p className="mt-3 text-balance text-sm leading-relaxed text-muted-foreground md:text-base">
          {t("footer.tagline")}
        </p>
        <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
          <Link to="/courses">
            <Button>{t("dashboard.browseAllCta")}</Button>
          </Link>
          <Link to="/login">
            <Button variant="ghost">{t("common.signIn")}</Button>
          </Link>
        </div>
      </div>
    )
  }

  return (
    <div className="container mx-auto px-4 py-6 sm:py-10">
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,3fr)_minmax(0,1fr)]">
        <div className="flex flex-col gap-6">
          <MyCoursesSection />
          <StreakCard />
        </div>
        <VerseOfTheDayCard />
      </div>
    </div>
  )
}
