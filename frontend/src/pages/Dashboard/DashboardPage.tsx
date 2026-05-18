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
import { MiniCalendar } from "@/components/dashboard/MiniCalendar"
import { cn } from "@/lib/utils"

const EDITORIAL_EASE = [0.22, 1, 0.36, 1] as const

/**
 * "My Courses" — the single tallest dashboard surface, so it gets its
 * own internal scroll: the dashboard's contract is "fits one viewport
 * + footer below the fold", and an arbitrary number of enrollments
 * can't be allowed to push the rest of the grid off the screen.
 *
 * ``i18n.language`` in the dep list re-fetches when the user flips
 * locale, so localised course titles update without a hard reload.
 */
function MyCoursesSection() {
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
    <section className="animate-fade-in flex h-full flex-col overflow-hidden rounded-md border border-border bg-card transition-[border-color] duration-300 hover:border-primary/25">
      <header className="flex items-center justify-between gap-3 border-b border-border bg-gradient-accent-subtle px-4 py-3 sm:px-5 sm:py-4">
        <div className="flex min-w-0 items-center gap-2.5">
          <BookOpen className="h-4 w-4 shrink-0 text-muted-foreground" strokeWidth={1.75} aria-hidden />
          <h2 className="truncate font-serif text-sm font-semibold tracking-tight text-foreground">
            {t("dashboard.myCourses")}
          </h2>
        </div>
        <Link
          to="/courses"
          className="inline-flex shrink-0 items-center gap-1 text-xs font-medium text-primary transition-opacity hover:opacity-80"
        >
          {t("dashboard.browseAllCta")}
          <ArrowRight className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
        </Link>
      </header>
      {/* Internal scroll. ``min-h-0`` + ``flex-1`` is the standard pattern
          for a scrollable region inside a flex column — without it the
          scroll container would size to its content, defeating the
          single-viewport contract on the dashboard wrapper. */}
      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-3 sm:px-5 sm:py-4">{body}</div>
    </section>
  )

  if (loading) {
    return shell(
      <div className="space-y-3">
        {Array.from({ length: 2 }).map((_, i) => (
          <div key={i} className="rounded-md border border-border/80 bg-muted/10 px-3 py-3">
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
        className="py-8"
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
        className="border-none bg-transparent px-4 py-8"
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
    <div className="stagger-fade-in flex flex-col gap-2.5">
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
              className="group block rounded-md border border-border/80 bg-muted/10 px-3 py-2.5 transition-colors hover:border-primary/30 hover:bg-muted/25"
            >
              <div className="flex items-center gap-3">
                <div className="min-w-0 flex-1">
                  <div className="flex items-start gap-2">
                    <h3 className="min-w-0 flex-1 truncate font-serif text-sm font-medium leading-tight text-foreground transition-colors duration-200 group-hover:text-primary">
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
                          transition={{
                            duration: 0.9,
                            delay: 0.15 + index * 0.045,
                            ease: EDITORIAL_EASE,
                          }}
                        />
                      )}
                    </div>
                    <span className="shrink-0 text-[11px] font-medium tabular-nums text-muted-foreground">
                      {enrollment.progress}%
                    </span>
                    {grade?.grade ? (
                      <span className="rounded-sm border border-border bg-background/80 px-1.5 py-0 text-[10px] font-medium text-foreground">
                        {grade.grade}
                      </span>
                    ) : null}
                  </div>
                </div>
                <ArrowRight
                  className="h-4 w-4 shrink-0 text-primary transition-transform duration-200 group-hover:translate-x-1"
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
 * **Single-viewport contract.** The whole page is laid out to fit in
 * one viewport on desktop (lg+) and a tight stack on mobile. The
 * footer sits below the fold via ``min-h-[calc(100dvh-headerH)]`` on
 * the main element (see ``App.tsx``).
 *
 * **Layout.** Two-column on lg+: My Courses (wide, with internal
 * scroll) takes the left column; Verse + MiniCalendar + Streak stack
 * in the narrow right rail. On smaller screens everything collapses
 * to a single column in importance order (My Courses → Streak →
 * Verse → MiniCalendar).
 */
export default function DashboardPage() {
  const { t } = useTranslation()
  const { user } = useAuth()

  if (!user) {
    // Guests get the splash that bounces to the catalog or login.
    return (
      <div className="container mx-auto flex max-w-2xl flex-col items-center justify-center px-4 py-16 text-center sm:py-24">
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
    <div className="container mx-auto h-full px-4 py-4 sm:py-6 lg:h-[calc(100dvh-3rem-3rem)]">
      {/* The ``lg:h-[calc(100dvh-3rem-3rem)]`` constraint (viewport
          minus header h-12 minus container py-6) caps the grid height
          on desktop so each card fills its share of one viewport
          instead of expanding indefinitely. Below lg the grid is
          natural-height; ``flex flex-col`` so a tall mobile stack
          still has a sane outline. */}
      <div className="grid h-full grid-cols-1 gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)] lg:gap-5">
        <MyCoursesSection />
        <div className="flex flex-col gap-4 lg:gap-5 lg:overflow-hidden">
          <div className="lg:min-h-0 lg:flex-shrink lg:overflow-hidden">
            <VerseOfTheDayCard />
          </div>
          <div className="lg:min-h-0 lg:flex-shrink lg:overflow-hidden">
            <MiniCalendar />
          </div>
          <div className="lg:min-h-0 lg:flex-shrink lg:overflow-hidden">
            <StreakCard />
          </div>
        </div>
      </div>
    </div>
  )
}
