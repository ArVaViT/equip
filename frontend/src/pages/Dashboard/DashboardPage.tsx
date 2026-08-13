import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { Link } from "react-router-dom"
import { motion, useReducedMotion } from "motion/react"
import { Button } from "@/components/ui/button"
import { coursesService } from "@/services/courses"
import type { Enrollment, StudentGrade } from "@/types"
import { useAuth } from "@/context/useAuth"
import { ArrowRight, BookOpen, CheckCircle } from "lucide-react"
import { ErrorState } from "@/components/patterns"
import { Skeleton } from "@/components/ui/skeleton"
import { VerseOfTheDayCard } from "@/components/home/VerseOfTheDayCard"
import { DailyChallengeCard } from "@/components/dashboard/DailyChallengeCard"
import { TodayCard } from "@/components/dashboard/TodayCard"
import { WelcomeCard } from "@/components/dashboard/WelcomeCard"
import { RecentlyViewedRow } from "@/components/dashboard/RecentlyViewedRow"
import { useUserTour } from "@/hooks/useUserTour"
import { studentDashboardSteps } from "@/lib/tourSteps"
import { firstNameOf } from "@/lib/names"
import { PublicLanding } from "./PublicLanding"
import { cn } from "@/lib/utils"
import { EDITORIAL_EASE, MOTION_DURATION } from "@/lib/motion"
import { isNewcomer, visibleEnrollments } from "./myCourses"

interface MyCoursesSectionProps {
  /** Click handler wired by ``DashboardPage`` to start the dashboard
   *  tour. We pipe it down through this section because the only
   *  natural place to surface a "Take a tour" link visually is on the
   *  empty-state welcome card that lives here. */
  onTourStart: () => void
}

/**
 * "My Courses" — left column of the Dashboard, given its own internal
 * scroll so an arbitrary enrollment count can't push the rest of the
 * grid off the screen. ``i18n.language`` in the dep list re-fetches
 * on locale flip so localised course titles update without a hard
 * reload.
 */
function MyCoursesSection({ onTourStart }: MyCoursesSectionProps) {
  const { t, i18n } = useTranslation()
  const { user } = useAuth()
  const prefersReducedMotion = useReducedMotion()
  const [enrollments, setEnrollments] = useState<Enrollment[]>([])
  const [grades, setGrades] = useState<StudentGrade[]>([])
  const [loading, setLoading] = useState(true)
  const [fetchError, setFetchError] = useState(false)
  const [retryCount, setRetryCount] = useState(0)

  useEffect(() => {
    let cancelled = false
    const load = async () => {
      setLoading(true)
      setFetchError(false)
      try {
        const [enrollData, gradeData] = await Promise.all([
          coursesService.getMyCourses(),
          // `[]` is honest here, unlike the same shape elsewhere. A missing
          // grade renders nothing at all — identical to a course that has not
          // been graded yet — so a failed request hides an optional badge
          // rather than asserting something false. Checked rather than
          // assumed: `grades` has exactly one consumer, the override chip.
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

  const filtered = visibleEnrollments(enrollments)
  const newcomer = isNewcomer({ enrollments, loading, failed: fetchError })
  const headerLabel = newcomer
    ? t("onboarding.student.eyebrow")
    : t("dashboard.myCourses")

  const shell = (body: React.ReactNode, centered = false) => (
    <section
      data-tour="my-courses"
      className="animate-fade-in flex h-full flex-col overflow-hidden rounded-md border border-edge dark:border-transparent bg-card transition-[border-color] duration-300 hover:border-brand/25"
    >
      <header className="flex items-center justify-between gap-3 border-b border-edge bg-gradient-accent-subtle px-4 py-3 sm:px-5 sm:py-4">
        <div className="flex min-w-0 items-center gap-2.5">
          <BookOpen className="h-4 w-4 shrink-0 text-ink-muted" strokeWidth={1.75} aria-hidden />
          <h2 className="truncate font-serif text-sm font-semibold tracking-tight text-ink">
            {headerLabel}
          </h2>
        </div>
        <Link
          to="/courses"
          className="inline-flex shrink-0 items-center gap-1 text-xs font-medium text-brand transition-opacity hover:opacity-80"
        >
          {t("dashboard.browseAllCta")}
          <ArrowRight className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
        </Link>
      </header>
      {/* ``centered`` flips the body to flex-center so empty- and
          error-states sit vertically in the middle of the scrollable
          area instead of clinging to the top edge. ``min-h-0`` lets the
          flex item shrink inside the column. */}
      <div
        className={cn(
          "min-h-0 flex-1 overflow-y-auto px-4 py-3 sm:px-5 sm:py-4",
          centered && "flex items-center justify-center",
        )}
      >
        {body}
      </div>
    </section>
  )

  if (loading) {
    return shell(
      <div className="w-full space-y-3">
        {Array.from({ length: 2 }).map((_, i) => (
          <div key={i} className="rounded-md bg-muted/10 px-3 py-3">
            <Skeleton className="h-4 w-3/5" />
            <Skeleton className="mt-2.5 h-1.5 w-2/3 rounded-full" />
          </div>
        ))}
      </div>,
    )
  }

  if (fetchError) {
    return shell(
      <ErrorState
        className="py-2"
        title={t("dashboard.loadCoursesError")}
        action={
          <Button type="button" variant="outline" size="sm" onClick={() => setRetryCount((c) => c + 1)}>
            {t("common.tryAgain")}
          </Button>
        }
      />,
      true,
    )
  }

  if (filtered.length === 0) {
    const firstName = firstNameOf(user?.full_name)
    return shell(
      <WelcomeCard
        eyebrow={t("onboarding.student.eyebrow")}
        title={
          firstName
            ? t("onboarding.student.title", { name: firstName })
            : t("onboarding.student.titleNoName")
        }
        description={t("onboarding.student.body")}
        action={
          <div className="flex flex-col items-center gap-2 sm:flex-row">
            <Link to="/courses">
              <Button size="sm">{t("onboarding.student.primaryCta")}</Button>
            </Link>
            <Button
              type="button"
              size="sm"
              variant="ghost"
              onClick={onTourStart}
              className="text-ink-muted hover:text-ink"
            >
              {t("tour.takeATour")}
            </Button>
          </div>
        }
      />,
      true,
    )
  }

  return shell(
    <div className="stagger-fade-in flex flex-col gap-2.5">
      {filtered
        .filter((e) => e.course?.id)
        .map((enrollment, index) => {
          const grade = grades.find((g) => g.course_id === enrollment.course_id)
          const progressColor = enrollment.progress >= 100 ? "bg-success" : "bg-brand"
          const courseId = enrollment.course!.id

          return (
            <Link
              key={enrollment.id}
              to={`/courses/${courseId}`}
              style={{ "--stagger-index": index } as React.CSSProperties}
              className="group block rounded-md bg-muted/10 px-3 py-2.5 transition-colors hover:border-brand/30 hover:bg-muted/40"
            >
              <div className="flex items-center gap-3">
                <div className="min-w-0 flex-1">
                  <div className="flex items-start gap-2">
                    <h3 className="min-w-0 flex-1 truncate font-serif text-sm font-medium leading-tight text-ink transition-colors duration-200 group-hover:text-brand">
                      {enrollment.course?.title || t("dashboard.course")}
                    </h3>
                    {enrollment.progress >= 100 && (
                      <CheckCircle className="h-3.5 w-3.5 shrink-0 text-success" strokeWidth={1.75} aria-hidden />
                    )}
                  </div>
                  <div className="mt-1.5 flex items-center gap-2">
                    <div className="h-1.5 min-w-20 flex-1 overflow-hidden rounded-full bg-muted">
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
                          // Was 0.9s with a 45ms-per-row stagger. A progress
                          // bar that fills is a nice touch; six of them
                          // filling in sequence over most of a second, on the
                          // screen you open every day, is a loading animation
                          // pretending to be a feature. One duration from the
                          // shared scale, no stagger.
                          transition={{ duration: MOTION_DURATION.panel, ease: EDITORIAL_EASE }}
                        />
                      )}
                    </div>
                    <span className="shrink-0 text-xs font-medium tabular-nums text-ink-muted">
                      {enrollment.progress}%
                    </span>
                    {grade?.override_code ? (
                      <span className="rounded-sm bg-surface/80 px-1.5 py-0 text-xs font-medium text-ink">
                        {grade.override_code}
                      </span>
                    ) : null}
                  </div>
                </div>
                <ArrowRight
                  className="h-4 w-4 shrink-0 text-brand transition-transform duration-200 group-hover:translate-x-1"
                  strokeWidth={1.75}
                  aria-hidden
                />
              </div>
            </Link>
          )
        })}
    </div>,
  )
}

/**
 * Authenticated dashboard at ``/``.
 *
 * **Single-viewport contract.** Footer sits below the fold via
 * ``min-h-[calc(100dvh-headerH)]`` on the main element (App.tsx).
 *
 * **Layout (lg+).** Two columns:
 * - Left (wider): My Courses with internal scroll.
 * - Right (narrow): Verse + Today + Daily Challenge distributed by need
 *   (``[auto auto minmax(0,1fr)]``) — the two light cards take exactly
 *   their content height so they never scroll, and Daily Challenge takes
 *   the remainder so its question + options fit. The whole rail stays
 *   inside the viewport and nothing scrolls.
 *
 * **Mobile (< lg).** Single column stack in importance order: My
 * Courses → Verse → Today → Streak.
 */
export default function DashboardPage() {
  const { user } = useAuth()
  const { t } = useTranslation()
  // The tour itself is locale-aware via ``useUserTour``; ``i18n`` here
  // is just for ``t`` to build the steps. ``useMemo`` so the array
  // reference is stable across re-renders that don't change locale.
  const tourSteps = studentDashboardSteps(t)
  const { start: startTour } = useUserTour({
    tourId: "student-dashboard-v1",
    steps: tourSteps,
  })

  if (!user) {
    return <PublicLanding />
  }

  return (
    <div className="container mx-auto h-full px-4 py-4 sm:py-6 lg:h-[calc(100dvh-3rem-3rem)]">
      <div className="grid h-full grid-cols-1 gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)] lg:gap-5">
        {/* Left column: an optional "recently viewed" strip (renders
            nothing when empty, so it costs no vertical space for new
            users) above the scrollable My Courses panel. ``min-h-0``
            lets My Courses keep its own internal scroll within the
            single-viewport grid. */}
        <div className="flex min-h-0 flex-col gap-4 lg:gap-5">
          <RecentlyViewedRow />
          <div className="min-h-0 flex-1">
            <MyCoursesSection onTourStart={startTour} />
          </div>
        </div>
        {/* Right rail on lg+ as ``[auto auto minmax(0,1fr)]``. Verse and
            Today are light, bounded cards (a single verse; at most three
            events) so they take exactly their content height (``auto``)
            and never grow an internal scrollbar. Daily Challenge — the
            tallest, interactive card — takes the remaining space
            (``minmax(0,1fr)``), so its question + four options sit in one
            viewport. Nothing on the dashboard scrolls; the rail just
            distributes by need instead of forcing equal slots. */}
        <div className="flex flex-col gap-4 lg:grid lg:grid-rows-[auto_auto_minmax(0,1fr)] lg:gap-5 lg:overflow-hidden">
          <div data-tour="verse-of-day" className="lg:min-h-0 lg:overflow-hidden">
            <VerseOfTheDayCard />
          </div>
          <div data-tour="today" className="lg:min-h-0 lg:overflow-hidden">
            <TodayCard />
          </div>
          <div data-tour="daily-challenge" className="lg:min-h-0 lg:overflow-hidden">
            <DailyChallengeCard />
          </div>
        </div>
      </div>
    </div>
  )
}
