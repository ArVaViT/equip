import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { Link } from "react-router-dom"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import { coursesService } from "@/services/courses"
import type { Course, Enrollment, StudentGrade } from "@/types"
import { useAuth } from "@/context/useAuth"
import { useDebouncedSearchParam } from "@/hooks/useDebouncedSearchParam"
import CourseCard from "@/components/course/CourseCard"
import CourseCardSkeleton from "@/components/skeletons/CourseCardSkeleton"
import { Search, BookOpen, LogIn, ArrowRight, CheckCircle } from "lucide-react"
import { EmptyState, ErrorState } from "@/components/patterns"
import { Skeleton } from "@/components/ui/skeleton"
import { cn } from "@/lib/utils"

function MyCoursesSectionHeader() {
  const { t } = useTranslation()
  return (
    <div className="border-b border-border bg-gradient-accent-subtle px-5 py-6 sm:px-8">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:gap-6">
        <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-md border border-border/80 bg-card shadow-none">
          <BookOpen className="h-6 w-6 text-muted-foreground" strokeWidth={1.75} aria-hidden />
        </div>
        <div className="min-w-0">
          <h2 className="font-serif text-xl font-semibold tracking-tight text-foreground sm:text-2xl">
            {t("home.myCourses")}
          </h2>
          <p className="mt-1.5 max-w-2xl text-sm leading-relaxed text-muted-foreground">{t("home.myCoursesLead")}</p>
        </div>
      </div>
    </div>
  )
}

function MyCoursesSectionBody({ children }: { children: React.ReactNode }) {
  return <div className="px-5 py-5 sm:px-8 sm:py-6">{children}</div>
}

function MyCoursesSection() {
  const { t } = useTranslation()
  const { user } = useAuth()
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
  }, [user?.id, retryCount])

  const filtered = enrollments.filter((e) => e.course?.created_by !== user?.id)

  const shell = (body: React.ReactNode) => (
    <section className="animate-fade-in mb-12 overflow-hidden rounded-md border border-border bg-card transition-[border-color] duration-300 hover:border-primary/25">
      <MyCoursesSectionHeader />
      <MyCoursesSectionBody>{body}</MyCoursesSectionBody>
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
        title={t("home.loadCoursesError")}
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
        title={t("home.myCoursesEmptyTitle")}
        description={t("home.noEnrollments")}
      />,
    )
  }

  return shell(
    <div className="stagger-fade-in flex flex-col gap-4">
      {filtered
        .filter((e) => e.course?.id)
        .map((enrollment, index) => {
        const grade = grades.find((g) => g.course_id === enrollment.course_id)
        const progressColor =
          enrollment.progress >= 100 ? "bg-success" : "bg-primary"
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
                    {enrollment.course?.title || t("home.course")}
                  </h3>
                  {enrollment.progress >= 100 && (
                    <CheckCircle className="mt-0.5 h-4 w-4 shrink-0 text-success" strokeWidth={1.75} aria-hidden />
                  )}
                </div>
                <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
                  <div className="flex min-w-0 flex-1 items-center gap-3 sm:max-w-md">
                    <div className="h-2 min-w-28 flex-1 rounded-full bg-muted">
                      <div
                        className={cn(
                          "h-full rounded-full transition-[width] duration-700 ease-out",
                          progressColor,
                        )}
                        style={{ width: `${Math.min(enrollment.progress, 100)}%` }}
                      />
                    </div>
                    <span className="shrink-0 text-xs font-medium tabular-nums text-muted-foreground">
                      {enrollment.progress}%
                    </span>
                  </div>
                  {grade?.grade ? (
                    <span className="rounded-md border border-border bg-background/80 px-2 py-0.5 text-xs font-medium text-foreground">
                      {t("home.grade", { grade: grade.grade })}
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

export default function HomePage() {
  const { t } = useTranslation()
  const { user } = useAuth()
  const { input, setInput, value: query, maxLength } = useDebouncedSearchParam()
  const [courses, setCourses] = useState<Course[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [reloadKey, setReloadKey] = useState(0)

  useEffect(() => {
    const signal = { cancelled: false }
    setLoading(true)
    setError(null)
    coursesService
      .getCourses(query || undefined)
      .then((data) => {
        if (!signal.cancelled) setCourses(data)
      })
      .catch(() => {
        if (!signal.cancelled) setError(t("home.loadFailed"))
      })
      .finally(() => {
        if (!signal.cancelled) setLoading(false)
      })
    return () => { signal.cancelled = true }
  }, [query, reloadKey, t])

  return (
    <div className="container mx-auto px-4 py-10">
      {user && <MyCoursesSection />}

      <section className="relative mb-14 md:mb-20" aria-labelledby="home-catalog-heading">
        <div className="pointer-events-none absolute left-1/2 top-0 -z-0 h-[min(22rem,55vw)] w-[min(120vw,44rem)] -translate-x-1/2 md:h-[26rem] md:w-[52rem]">
          <div className="bg-home-hero-glow h-full w-full blur-3xl" aria-hidden />
        </div>
        <div className="relative z-10 mx-auto max-w-2xl px-4 pb-2 pt-6 text-center md:pt-10">
          <p className="animate-fade-in text-xs font-medium uppercase tracking-[0.22em] text-primary/90 mb-3">
            {t("home.academicPrograms")}
          </p>
          <h1
            id="home-catalog-heading"
            className="animate-fade-in animate-delay-100 text-balance font-serif text-3xl font-bold tracking-tight text-foreground sm:text-4xl"
          >
            {user ? t("home.browseCourses") : t("home.courseCatalog")}
          </h1>
          <p className="animate-fade-in animate-delay-200 mt-3 text-balance text-sm leading-relaxed text-muted-foreground md:text-base">
            {user ? t("home.discoverMore") : t("home.browseSeminary")}
          </p>
          <div className="animate-fade-in animate-delay-300 relative mx-auto mt-8 max-w-md">
            <Search
              className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground"
              strokeWidth={1.75}
              aria-hidden
            />
            <Input
              value={input}
              onChange={(e) => setInput(e.target.value.slice(0, maxLength))}
              maxLength={maxLength}
              placeholder={t("home.searchPlaceholder")}
              className="rounded-md border-border/80 bg-background/85 pl-9 backdrop-blur-sm focus-visible:ring-2"
              aria-label={t("home.searchPlaceholder")}
            />
          </div>
        </div>
      </section>

      {!user && (
        <div className="mb-8 flex items-center justify-center gap-2 rounded-md border border-border border-l-[3px] border-l-info bg-info/5 px-4 py-3">
          <LogIn className="h-4 w-4 text-info" strokeWidth={1.75} aria-hidden="true" />
          <p className="text-sm text-foreground">
            <Link
              to="/login"
              className="font-medium underline underline-offset-2 hover:no-underline"
            >
              {t("home.signInLink")}
            </Link>{" "}
            {t("home.signInToEnroll")}
          </p>
        </div>
      )}

      {loading ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-7">
          {Array.from({ length: 6 }).map((_, i) => <CourseCardSkeleton key={i} />)}
        </div>
      ) : error ? (
        <ErrorState
          icon={<BookOpen />}
          description={error}
          action={
            <Button variant="ghost" size="sm" onClick={() => setReloadKey((k) => k + 1)}>
              {t("common.tryAgain")}
            </Button>
          }
        />
      ) : courses.length === 0 ? (
        <EmptyState
          icon={<BookOpen />}
          title={query ? t("home.noCoursesFound") : t("home.noCoursesYet")}
          description={query ? t("home.tryDifferentSearch") : t("home.checkBackSoon")}
          className="border-none bg-transparent py-20"
        />
      ) : (
        <div className="stagger-fade-in grid grid-cols-1 gap-7 sm:grid-cols-2 lg:grid-cols-3">
          {courses.map((course, index) => (
            <CourseCard
              key={course.id}
              course={course}
              style={{ "--stagger-index": index } as React.CSSProperties}
            />
          ))}
        </div>
      )}
    </div>
  )
}
