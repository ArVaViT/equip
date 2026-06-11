import { useMemo } from "react"
import { useTranslation } from "react-i18next"
import { Link } from "react-router-dom"
import { History, BookOpen } from "lucide-react"
import { coursesService } from "@/services/courses"
import { useAsyncData } from "@/hooks/useAsyncData"
import { useAuth } from "@/context/useAuth"
import { getRecentCourses } from "@/lib/recentlyViewed"
import type { Enrollment } from "@/types"

/**
 * "Recently viewed" — a compact horizontal row of the last few courses
 * the student opened (tracked in localStorage by ``recordCourseView``).
 *
 * The localStorage list is just opaque course IDs; we intersect it with
 * the user's real enrollments (``getMyCourses``, the same 1-min-cached
 * call ``MyCoursesSection`` already makes, so no extra round-trip on a
 * normal dashboard load) to (a) resolve titles and (b) drop stale IDs
 * for courses the student no longer has access to. Renders nothing when
 * the intersection is empty, so a brand-new user never sees an empty
 * shell.
 */
export function RecentlyViewedRow() {
  const { t, i18n } = useTranslation()
  const { user } = useAuth()
  const { data: enrollments } = useAsyncData<Enrollment[]>(
    async () => (user ? coursesService.getMyCourses().catch(() => []) : []),
    [user?.id, i18n.language],
  )

  const recent = useMemo(() => {
    const byId = new Map<string, Enrollment>()
    for (const e of enrollments ?? []) {
      if (e.course?.id) byId.set(e.course.id, e)
    }
    return getRecentCourses()
      .map((r) => byId.get(r.id))
      .filter((e): e is Enrollment => !!e)
      .slice(0, 5)
  }, [enrollments])

  if (recent.length === 0) return null

  return (
    <section aria-labelledby="recently-viewed-heading" className="animate-fade-in">
      <div className="mb-2 flex items-center gap-2">
        <History className="h-4 w-4 shrink-0 text-ink-muted" strokeWidth={1.75} aria-hidden />
        <h2
          id="recently-viewed-heading"
          className="font-serif text-sm font-semibold tracking-tight text-ink"
        >
          {t("dashboard.recentlyViewed")}
        </h2>
      </div>
      <ul className="flex gap-2.5 overflow-x-auto pb-1">
        {recent.map((enrollment) => {
          const course = enrollment.course!
          return (
            <li key={course.id} className="shrink-0">
              <Link
                to={`/courses/${course.id}`}
                className="group flex w-44 items-center gap-2 rounded-md border border-edge bg-card px-3 py-2 transition-colors hover:border-brand/30 hover:bg-muted/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 focus-visible:ring-offset-background"
              >
                <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-brand/10 text-brand">
                  <BookOpen className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
                </span>
                <span className="min-w-0 flex-1 truncate font-serif text-xs font-medium leading-tight text-ink transition-colors group-hover:text-brand">
                  {course.title || t("dashboard.course")}
                </span>
              </Link>
            </li>
          )
        })}
      </ul>
    </section>
  )
}
