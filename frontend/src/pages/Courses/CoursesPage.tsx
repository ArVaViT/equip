import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { Link } from "react-router-dom"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import { coursesService } from "@/services/courses"
import type { Course } from "@/types"
import { useAuth } from "@/context/useAuth"
import { useDebouncedSearchParam } from "@/hooks/useDebouncedSearchParam"
import CourseCard from "@/components/course/CourseCard"
import CourseCardSkeleton from "@/components/skeletons/CourseCardSkeleton"
import { Search, BookOpen, LogIn } from "lucide-react"
import { EmptyState, ErrorState } from "@/components/patterns"
import { useUserTour } from "@/hooks/useUserTour"
import { coursesCatalogSteps } from "@/lib/tourSteps"

/**
 * Public course catalog. Lifted out of the old HomePage when the
 * landing route became a Dashboard. Identical browse/search/grid
 * behavior; only the surrounding chrome changed (no "My Courses"
 * + Verse-of-the-Day rail above the hero).
 *
 * Locale: ``i18n.language`` is included in the fetch effect so a
 * locale flip re-pulls the catalog and the translation overlay
 * lands without a hard reload. The api interceptor sends
 * ``Accept-Language`` per request and bakes the locale into the
 * dedupe key (see services/api.ts), so this triggers a real
 * round-trip rather than serving a cached payload.
 */
export default function CoursesPage() {
  const { t, i18n } = useTranslation()
  const { user } = useAuth()
  const { input, setInput, value: query, maxLength } = useDebouncedSearchParam()
  const [courses, setCourses] = useState<Course[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [reloadKey, setReloadKey] = useState(0)
  useUserTour({
    tourId: "courses-catalog-v1",
    steps: coursesCatalogSteps(t),
    ready: !loading && !error,
  })

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
        if (!signal.cancelled) setError(t("courses.loadFailed"))
      })
      .finally(() => {
        if (!signal.cancelled) setLoading(false)
      })
    return () => {
      signal.cancelled = true
    }
  }, [query, reloadKey, t, i18n.language])

  return (
    <div className="container mx-auto px-4 py-6 sm:py-10">
      <section className="relative mb-10 md:mb-20" aria-labelledby="courses-catalog-heading">
        <div className="pointer-events-none absolute left-1/2 top-0 -z-0 h-[min(22rem,55vw)] w-[min(120vw,44rem)] -translate-x-1/2 md:h-[26rem] md:w-[52rem]">
          <div className="bg-home-hero-glow h-full w-full blur-3xl" aria-hidden />
        </div>
        <div className="relative z-10 mx-auto max-w-2xl px-4 pb-2 pt-6 text-center md:pt-10">
          <p className="animate-fade-in text-xs font-medium uppercase tracking-[0.22em] text-primary/90 mb-3">
            {t("courses.academicPrograms")}
          </p>
          <h1
            id="courses-catalog-heading"
            className="animate-fade-in animate-delay-100 text-balance font-serif text-3xl font-bold tracking-tight text-gradient-primary sm:text-4xl"
          >
            {user ? t("courses.pageTitleAuthed") : t("courses.pageTitle")}
          </h1>
          <p className="animate-fade-in animate-delay-200 mt-3 text-balance text-sm leading-relaxed text-muted-foreground md:text-base">
            {user ? t("courses.pageSubtitleAuthed") : t("courses.pageSubtitle")}
          </p>
          <div data-tour="catalog-search" className="animate-fade-in animate-delay-300 relative mx-auto mt-8 max-w-md">
            <Search
              className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground"
              strokeWidth={1.75}
              aria-hidden
            />
            <Input
              value={input}
              onChange={(e) => setInput(e.target.value.slice(0, maxLength))}
              maxLength={maxLength}
              placeholder={t("courses.searchPlaceholder")}
              className="rounded-md border-border/80 bg-background/85 pl-9 backdrop-blur-sm focus-visible:ring-2"
              aria-label={t("courses.searchPlaceholder")}
            />
          </div>
        </div>
      </section>

      {!user && (
        <div className="mb-8 flex flex-wrap items-center justify-center gap-x-2 gap-y-1 rounded-md border border-border border-l-[3px] border-l-info bg-info/5 px-4 py-3 text-center sm:text-left">
          <LogIn className="h-4 w-4 shrink-0 text-info" strokeWidth={1.75} aria-hidden="true" />
          <p className="text-sm text-foreground">
            <Link
              to="/login"
              className="-my-2 inline-flex min-h-[44px] items-center font-medium underline underline-offset-2 hover:no-underline sm:my-0 sm:min-h-0"
            >
              {t("courses.signInLink")}
            </Link>{" "}
            {t("courses.signInToEnroll")}
          </p>
        </div>
      )}

      {loading ? (
        <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 sm:gap-7 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <CourseCardSkeleton key={i} />
          ))}
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
          title={query ? t("courses.noCoursesFound") : t("courses.noCoursesYet")}
          description={query ? t("courses.tryDifferentSearch") : t("courses.checkBackSoon")}
          className="border-none bg-transparent py-20"
        />
      ) : (
        <div data-tour="catalog-grid" className="stagger-fade-in grid grid-cols-1 gap-5 sm:grid-cols-2 sm:gap-7 lg:grid-cols-3">
          {courses.map((course, index) => (
            <CourseCard key={course.id} course={course} style={{ "--stagger-index": index } as React.CSSProperties} />
          ))}
        </div>
      )}
    </div>
  )
}
