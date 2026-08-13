import { useEffect, useMemo, useState } from "react"
import { useTranslation } from "react-i18next"
import { Link } from "react-router-dom"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import { coursesService } from "@/services/courses"
import type { Course } from "@/types"
import { useAuth } from "@/context/useAuth"
import { useAsyncData } from "@/hooks/useAsyncData"
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
// First-page size for the catalog. Smaller than the backend cap (200) so the
// first paint is fast; the rest loads on demand via "load more". Before this,
// the UI fetched the default 100 and silently dropped anything past it.
const PAGE_SIZE = 24

export default function CoursesPage() {
  const { t, i18n } = useTranslation()
  const { user } = useAuth()
  const { input, setInput, value: query, maxLength } = useDebouncedSearchParam()
  const [courses, setCourses] = useState<Course[]>([])
  const [reloadKey, setReloadKey] = useState(0)
  const [hasMore, setHasMore] = useState(false)
  const [loadingMore, setLoadingMore] = useState(false)
  const [moreError, setMoreError] = useState(false)
  const { data: fetchedCourses, loading, error: fetchError } = useAsyncData(
    async () => coursesService.getCourses(query || undefined, { skip: 0, limit: PAGE_SIZE }),
    // ``i18n.language`` triggers a refetch on locale flip so localised
    // titles/descriptions re-pull. ``t`` is intentionally not a dep —
    // its reference-change behaviour is implementation-defined.
    [query, reloadKey, i18n.language],
  )
  // Enrollment progress for the signed-in viewer, so each catalog card
  // can show a completion bar for courses they're enrolled in. ONE call
  // to the (1-min cached, shared) ``getMyCourses`` endpoint — not a
  // per-card fetch. Anonymous users skip it entirely and see plain
  // cards. A failure degrades silently to "no bars".
  const { data: myEnrollments } = useAsyncData(
    async () => (user ? coursesService.getMyCourses().catch(() => []) : []),
    [user?.id],
  )
  const progressByCourseId = useMemo(() => {
    const map = new Map<string, number>()
    for (const e of myEnrollments ?? []) {
      if (e.course_id) map.set(e.course_id, e.progress)
    }
    return map
  }, [myEnrollments])
  // Token-key error so a locale flip while the error is on screen
  // updates the message without a refetch.
  const error: string | null = fetchError ? t("courses.loadFailed") : null
  useUserTour({
    tourId: "courses-catalog-v1",
    steps: coursesCatalogSteps(t),
    ready: !loading && !error,
  })

  // Sync the useAsyncData result into the existing courses state so the
  // (search/filter) downstream logic can continue to read from a single
  // source of truth without restructuring the rest of the file.
  useEffect(() => {
    if (fetchedCourses !== undefined) {
      setCourses(fetchedCourses)
      // A full page back means there may be more; a short page is the end.
      setHasMore(fetchedCourses.length === PAGE_SIZE)
      setMoreError(false)
    }
  }, [fetchedCourses])

  // Append the next page. skip = current count (catalog order is stable
  // created_at desc, so offset paging is correct for append).
  const loadMore = async () => {
    setLoadingMore(true)
    setMoreError(false)
    try {
      const next = await coursesService.getCourses(query || undefined, { skip: courses.length, limit: PAGE_SIZE })
      setCourses((prev) => [...prev, ...next])
      setHasMore(next.length === PAGE_SIZE)
    } catch {
      setMoreError(true)
    } finally {
      setLoadingMore(false)
    }
  }

  return (
    <div className="container mx-auto px-4 py-6 sm:py-10">
      <section className="relative mb-10 md:mb-20" aria-labelledby="courses-catalog-heading">
        <div className="relative z-10 mx-auto max-w-2xl px-4 pb-2 pt-6 text-center md:pt-10">
          <p className="animate-fade-in text-xs font-medium uppercase tracking-[0.22em] text-brand mb-3">
            {t("courses.academicPrograms")}
          </p>
          <h1
            id="courses-catalog-heading"
            className="animate-fade-in animate-delay-100 text-balance font-serif text-3xl font-bold tracking-tight text-ink sm:text-4xl"
          >
            {user ? t("courses.pageTitleAuthed") : t("courses.pageTitle")}
          </h1>
          <p className="animate-fade-in animate-delay-200 mt-3 text-balance text-sm leading-relaxed text-ink-muted md:text-base">
            {user ? t("courses.pageSubtitleAuthed") : t("courses.pageSubtitle")}
          </p>
          <div data-tour="catalog-search" className="animate-fade-in animate-delay-300 relative mx-auto mt-8 max-w-md">
            <Search
              className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-muted"
              strokeWidth={1.75}
              aria-hidden
            />
            <Input
              value={input}
              onChange={(e) => setInput(e.target.value.slice(0, maxLength))}
              maxLength={maxLength}
              placeholder={t("courses.searchPlaceholder")}
              className="rounded-md pl-9 focus-visible:ring-2"
              aria-label={t("courses.searchPlaceholder")}
            />
          </div>
        </div>
      </section>

      {!user && (
        <div className="mb-8 flex flex-wrap items-center justify-center gap-x-2 gap-y-1 rounded-md border-l-[3px] border-l-info bg-info/5 px-4 py-3 text-center sm:text-left">
          <LogIn className="h-4 w-4 shrink-0 text-info-ink" strokeWidth={1.75} aria-hidden="true" />
          <p className="text-sm text-ink">
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
          icon={<BookOpen strokeWidth={1.75} aria-hidden />}
          description={error}
          action={
            <Button variant="ghost" size="sm" onClick={() => setReloadKey((k) => k + 1)}>
              {t("common.tryAgain")}
            </Button>
          }
        />
      ) : courses.length === 0 ? (
        <EmptyState
          icon={<BookOpen strokeWidth={1.75} aria-hidden />}
          title={query ? t("courses.noCoursesFound") : t("courses.noCoursesYet")}
          description={query ? t("courses.tryDifferentSearch") : t("courses.checkBackSoon")}
          className="border-none bg-transparent py-20"
        />
      ) : (
        <div data-tour="catalog-grid" className="stagger-fade-in grid grid-cols-1 gap-5 sm:grid-cols-2 sm:gap-7 lg:grid-cols-3">
          {courses.map((course, index) => (
            <CourseCard
              key={course.id}
              course={course}
              progress={progressByCourseId.get(course.id)}
              style={{ "--stagger-index": index } as React.CSSProperties}
            />
          ))}
        </div>
      )}

      {!loading && !error && hasMore && (
        <div className="mt-10 flex justify-center">
          <Button variant="outline" onClick={loadMore} disabled={loadingMore}>
            {loadingMore ? t("courses.loadingMore") : t("courses.loadMore")}
          </Button>
        </div>
      )}
      {moreError && <p className="mt-4 text-center text-sm text-destructive">{t("courses.loadMoreFailed")}</p>}
    </div>
  )
}
