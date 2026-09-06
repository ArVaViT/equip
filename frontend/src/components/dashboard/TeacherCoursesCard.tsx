import { useTranslation } from "react-i18next"
import { Link } from "react-router-dom"
import { ArrowRight, GraduationCap, PenLine } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { useAsyncData } from "@/hooks/useAsyncData"
import { useAuth } from "@/context/useAuth"
import { coursesService } from "@/services/courses"
import { ROLES, type Course } from "@/types"

/** How many courses the card names before it says "and N more". */
const SHOWN = 3

const STATUS_KEY: Record<Course["status"], string> = {
  draft: "teacherDashboard.courseCard.statusDraft",
  publishing: "teacherDashboard.courseCard.statusPublishing",
  published: "teacherDashboard.courseCard.statusPublished",
}

const STATUS_VARIANT: Record<Course["status"], "success" | "warningSubtle" | "warning"> = {
  draft: "warning",
  publishing: "warningSubtle",
  published: "success",
}

/**
 * The teacher's courses, on the page every sign-in lands on.
 *
 * Signing in took a teacher to the student dashboard: "Welcome to Equip —
 * pick a topic that speaks to you", and nothing on the page said where
 * the course they had been writing all week had gone. The only way to it
 * was a header item called "Manage", a word nobody looking for their own
 * course thinks to click.
 *
 * This card sits at the top of the left column for anyone who teaches,
 * names their courses with a link into the editor for each, and points
 * at the teaching section for the rest. It adds to the page rather than
 * replacing it: a teacher is also a student here, and the verse, the
 * daily challenge and the courses they are enrolled in stay where they
 * were. Students never see it.
 *
 * It renders on its own fetch and fails on its own: a failed request
 * leaves the card in place with the link to the teaching section, which
 * is the one thing it must never lose.
 */
export function TeacherCoursesCard() {
  const { t, i18n } = useTranslation()
  const { user } = useAuth()
  const teaches = user?.role === ROLES.TEACHER || user?.role === ROLES.ADMIN
  const { data: courses, loading } = useAsyncData<Course[] | null>(
    async () => (teaches ? coursesService.getTeacherCourses().catch(() => null) : []),
    [user?.id, teaches, i18n.language],
  )

  if (!teaches) return null

  const list = courses ?? []
  const shown = list.slice(0, SHOWN)
  const rest = list.length - shown.length
  // `null` is a failed request, `[]` a teacher with no courses yet. The
  // two get different sentences: one says nothing about the courses, the
  // other invites the first.
  const failed = !loading && courses === null
  const empty = !loading && courses !== null && list.length === 0

  return (
    <section
      data-testid="teacher-courses-card"
      aria-labelledby="teacher-courses-heading"
      className="animate-fade-in rounded-md border border-edge bg-card dark:border-transparent"
    >
      <div className="flex flex-wrap items-center gap-3 px-4 py-3 sm:px-5">
        <span
          className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-brand/10 text-brand-ink"
          aria-hidden
        >
          <GraduationCap className="h-4 w-4" strokeWidth={1.75} />
        </span>
        <div className="min-w-0 flex-1">
          <h2
            id="teacher-courses-heading"
            className="font-serif text-sm font-semibold tracking-tight text-ink"
          >
            {t("dashboard.teaching.title")}
          </h2>
          <p className="mt-0.5 text-xs text-ink-muted">{t("dashboard.teaching.description")}</p>
        </div>
        <Link to="/teacher" className="shrink-0">
          <Button size="sm" variant={empty ? "default" : "outline"}>
            {empty ? t("dashboard.teaching.createFirst") : t("dashboard.teaching.openAll")}
            <ArrowRight className="ml-1.5 h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
          </Button>
        </Link>
      </div>

      {loading && (
        <div className="space-y-2 border-t border-edge px-4 py-3 sm:px-5 dark:border-white/5" aria-busy>
          <Skeleton className="h-4 w-2/3" />
          <Skeleton className="h-4 w-1/2" />
        </div>
      )}

      {empty && (
        <p className="border-t border-edge px-4 py-3 text-sm text-ink-muted sm:px-5 dark:border-white/5">
          {t("dashboard.teaching.empty")}
        </p>
      )}

      {!loading && !failed && shown.length > 0 && (
        <ul className="divide-y divide-edge border-t border-edge dark:divide-white/5 dark:border-white/5">
          {shown.map((course) => (
            <li key={course.id}>
              <Link
                to={`/teacher/courses/${course.id}`}
                className="group flex items-center gap-3 px-4 py-2.5 transition-colors hover:bg-muted/40 sm:px-5"
              >
                <span className="min-w-0 flex-1 truncate font-serif text-sm font-medium text-ink transition-colors group-hover:text-brand">
                  {course.title || t("dashboard.course")}
                </span>
                <Badge variant={STATUS_VARIANT[course.status]} className="shrink-0">
                  {t(STATUS_KEY[course.status])}
                </Badge>
                <span className="hidden shrink-0 items-center gap-1 text-xs text-ink-muted sm:inline-flex">
                  <PenLine className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
                  {t("dashboard.teaching.edit")}
                </span>
              </Link>
            </li>
          ))}
          {rest > 0 && (
            <li>
              <Link
                to="/teacher"
                className="block px-4 py-2 text-xs text-ink-muted transition-colors hover:text-ink sm:px-5"
              >
                {t("dashboard.teaching.more", { count: rest })}
              </Link>
            </li>
          )}
        </ul>
      )}
    </section>
  )
}
