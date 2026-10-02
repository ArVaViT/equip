import { useTranslation } from "react-i18next"
import { Link } from "react-router-dom"
import { useState } from "react"
import { ArrowRight, ChevronDown, GraduationCap, Pencil } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { useAsyncData } from "@/hooks/useAsyncData"
import { useAuth } from "@/context/useAuth"
import { CourseThumb } from "@/components/course/CourseThumb"
import { coursesService } from "@/services/courses"
import type { Course } from "@/types"
import { canTeach } from "@/lib/roles"
import { cn } from "@/lib/utils"

/** How many courses the card names before it says "and N more". */
const SHOWN = 3

/** Where the teaching card remembers whether it was left open. */
export const TEACHING_OPEN_KEY = "equip:dashboard:teaching-open"

function readOpen(): boolean {
  try {
    return localStorage.getItem(TEACHING_OPEN_KEY) === "1"
  } catch {
    return false
  }
}

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
  const teaches = canTeach(user?.role)
  const { data: courses, loading } = useAsyncData<Course[] | null>(
    async () => (teaches ? coursesService.getTeacherCourses().catch(() => null) : []),
    [user?.id, teaches, i18n.language],
  )

  const [openChoice, setOpenChoice] = useState(readOpen)

  if (!teaches) return null

  const list = courses ?? []
  const shown = list.slice(0, SHOWN)
  const rest = list.length - shown.length
  // `null` is a failed request, `[]` a teacher with no courses yet. The
  // two get different sentences: one says nothing about the courses, the
  // other invites the first.
  const failed = !loading && courses === null
  const empty = !loading && courses !== null && list.length === 0
  const collapsible = !loading && !failed && list.length > 0
  const open = !collapsible || openChoice
  const toggle = () => {
    const next = !openChoice
    setOpenChoice(next)
    try {
      localStorage.setItem(TEACHING_OPEN_KEY, next ? "1" : "0")
    } catch {
      /* private mode: the choice lasts the page, not the visit */
    }
  }

  const listShown = open && !loading && !failed && shown.length > 0
  return (
    <section
      data-testid="teacher-courses-card"
      aria-labelledby="teacher-courses-heading"
      className="animate-fade-in overflow-hidden rounded-card bg-card shadow-card"
    >
      {/* The same header as every other card on this page — an icon, the
          title, one quiet link on the right. It was a circled icon, a
          two-line explanation and an outline button: the one card on the
          page that talked, and the one link styled differently from
          «Открыть каталог» beside it («кнопки разные, хотя по идее это
          похожие кнопки»). */}
      <header
        className={cn(
          "flex items-center justify-between gap-3 bg-gradient-accent-subtle px-4 py-3 sm:px-5 sm:py-4",
          open && "border-b border-edge",
        )}
      >
        <h2 id="teacher-courses-heading" className="flex min-w-0 flex-1">
          {/* The whole title opens and closes the list — «можно скрыть под
              шеврон». Collapsed by default and remembered: a teacher who
              lands here every day knows what they teach, and the courses
              they are learning from sit right below. With no courses yet
              there is nothing to hide, and the invitation to create the
              first one stays in view. */}
          <button
            type="button"
            onClick={toggle}
            disabled={!collapsible}
            aria-expanded={open}
            // Only while the list is there: a reference to a missing id is an
            // invalid attribute value (axe, critical).
            aria-controls={listShown ? "teacher-courses-list" : undefined}
            className="group -mx-1 flex min-w-0 items-center gap-2.5 rounded-md px-1 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-default"
          >
            <GraduationCap className="h-4 w-4 shrink-0 text-ink-muted" strokeWidth={1.75} aria-hidden />
            <span className="truncate font-serif text-sm font-semibold tracking-tight text-ink">
              {t("dashboard.teaching.title")}
            </span>
            {collapsible && (
              <>
                <span className="shrink-0 rounded-full bg-muted px-1.5 text-xs font-medium tabular-nums text-ink-muted">
                  {list.length}
                </span>
                <ChevronDown
                  className={cn(
                    "h-4 w-4 shrink-0 text-ink-muted transition-transform duration-base group-hover:text-ink",
                    open && "rotate-180",
                  )}
                  strokeWidth={1.75}
                  aria-hidden
                />
              </>
            )}
          </button>
        </h2>
        <Link
          to="/teacher"
          className="inline-flex shrink-0 items-center gap-1 text-xs font-medium text-brand transition-opacity hover:opacity-80"
        >
          {/* The arrow alone on a phone, as on the calendar card: the words
              ran under the title and its chevron. They stay the link's name. */}
          <span className="max-sm:sr-only">{t("dashboard.teaching.openAll")}</span>
          <ArrowRight className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
        </Link>
      </header>

      {loading && (
        <div className="space-y-2 px-4 py-3 sm:px-5" aria-busy>
          <Skeleton className="h-4 w-2/3" />
          <Skeleton className="h-4 w-1/2" />
        </div>
      )}

      {empty && (
        <div className="flex flex-col items-start gap-3 px-4 py-3 sm:flex-row sm:items-center sm:px-5">
          <p className="flex-1 text-sm text-ink-muted">{t("dashboard.teaching.empty")}</p>
          {/* The link is the button — not a <button> inside an <a>, which is
              two tab stops and two roles for one action. */}
          <Button asChild size="sm" className="shrink-0">
            <Link to="/teacher">{t("dashboard.teaching.createFirst")}</Link>
          </Button>
        </div>
      )}

      {listShown && (
        <ul id="teacher-courses-list" className="divide-y divide-edge dark:divide-white/5">
          {shown.map((course) => (
            <li key={course.id}>
              <Link
                to={`/teacher/courses/${course.id}`}
                className="group flex items-center gap-3 px-4 py-2 transition-colors hover:bg-muted/40 sm:px-5"
              >
                <CourseThumb course={course} className="h-12 sm:h-14" />
                <span className="min-w-0 flex-1 truncate font-serif text-sm font-medium text-ink transition-colors group-hover:text-brand">
                  {course.title || t("dashboard.course")}
                </span>
                {/* On a phone the badge left the title nine letters. Published
                    is the ordinary state and goes quiet there; a draft or a
                    course still publishing keeps its badge on every width. */}
                <Badge
                  variant={STATUS_VARIANT[course.status]}
                  className={course.status === "published" ? "hidden shrink-0 sm:inline-flex" : "shrink-0"}
                >
                  {t(STATUS_KEY[course.status])}
                </Badge>
                {/* The pencil of the teaching page's own edit button, not
                    the words «Открыть в редакторе» on every row. The words
                    stay for a screen reader. */}
                <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-ink-muted transition-colors group-hover:bg-muted group-hover:text-ink">
                  <Pencil className="h-4 w-4" strokeWidth={1.75} aria-hidden />
                  <span className="sr-only">{t("dashboard.teaching.edit")}</span>
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
