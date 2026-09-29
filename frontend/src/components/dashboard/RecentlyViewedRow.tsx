import { useMemo } from "react"
import { useTranslation } from "react-i18next"
import { Link } from "react-router-dom"
import { History } from "lucide-react"
import { coursesService } from "@/services/courses"
import { useAsyncData } from "@/hooks/useAsyncData"
import { useAuth } from "@/context/useAuth"
import { getRecentCourses } from "@/lib/recentlyViewed"
import type { Enrollment } from "@/types"
import { CourseThumb } from "@/components/course/CourseThumb"

/**
 * The row appears once there are this many courses to put in it, and
 * shows exactly this many.
 *
 * It used to appear with one: a single small tile at the left of a strip
 * made for five, the rest of the width empty — «пустота когда открыто
 * меньше 5 курсов». Below five, "My courses" underneath already lists
 * every one of them, so the row added nothing but the gap.
 */
export const RECENT_ROW_SIZE = 5

/**
 * "Recently viewed" — a compact row of the last few courses
 * the student opened (tracked in localStorage by ``recordCourseView``).
 *
 * The localStorage list is just opaque course IDs; we intersect it with
 * the user's real enrollments (``getMyCourses``, the same 1-min-cached
 * call ``MyCoursesSection`` already makes, so no extra round-trip on a
 * normal dashboard load) to (a) resolve titles and (b) drop stale IDs
 * for courses the student no longer has access to. Renders nothing until
 * there are ``RECENT_ROW_SIZE`` of them.
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
      .slice(0, RECENT_ROW_SIZE)
  }, [enrollments])

  if (recent.length < RECENT_ROW_SIZE) return null

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
      {/* Five equal tiles across the column on a desktop; a strip to swipe
          on a phone, where five would not fit side by side. */}
      <ul className="-mx-1 flex gap-2.5 overflow-x-auto px-1 pb-1 sm:grid sm:grid-cols-5 sm:overflow-visible">
        {recent.map((enrollment) => {
          const course = enrollment.course!
          return (
            <li key={course.id} className="w-40 shrink-0 sm:w-auto">
              <Link
                to={`/courses/${course.id}`}
                className="lift group flex items-center gap-2 rounded-lg border border-edge bg-card p-1.5 pr-2.5 shadow-card hover:border-brand/30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 focus-visible:ring-offset-background dark:border-transparent"
              >
                <CourseThumb course={course} />
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
