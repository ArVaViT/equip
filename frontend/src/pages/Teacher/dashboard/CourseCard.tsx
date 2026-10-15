import { Link } from "react-router-dom"
import { useTranslation } from "react-i18next"
import {
  BarChart3,
  BookOpen,
  ClipboardList,
  Copy,
  Eye,
  EyeOff,
  Layers,
  Loader2,
  MoreHorizontal,
  Trash2,
  Users,
} from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { CourseCoverFallback } from "@/components/course/CourseCoverFallback"
import { toProxyImage } from "@/lib/images"
import { countChapters, countModules } from "@/lib/courseStructure"
import type { Course } from "@/types"

interface Props {
  course: Course
  /** Work waiting on the teacher in this course. 0 renders nothing —
      a badge that is always there stops being a signal. */
  pendingGrading?: number
  togglingId: string | null
  cloningId: string | null
  onToggleStatus: (course: Course) => void
  onClone: (id: string) => void
  onDelete: (id: string) => void
}

export function CourseCard({
  course,
  pendingGrading = 0,
  togglingId,
  cloningId,
  onToggleStatus,
  onClone,
  onDelete,
}: Props) {
  const { t } = useTranslation()
  // What the card is actually about: how much of the course is written.
  // ``modules.length`` was the only number here, and for a course that is
  // four lessons and no grouping it read "0 modules" — true, and a lie
  // about an empty course. The counts come from the server, so they are
  // right on a list payload that carries no chapter rows at all.
  const lessonCount = countChapters(course)
  const moduleCount = countModules(course)
  const isPublished = course.status === "published"
  // A course the teacher sent out that is not in the catalog yet: some
  // language does not have it, or a translation needs a person to look
  // at it. Its own badge, because "Draft" would be a lie — the teacher
  // did publish it — and "Published" would be a worse one.
  const isPublishing = course.status === "publishing"
  const isOut = isPublished || isPublishing
  const togglePublishLabel = isOut
    ? t("teacherDashboard.courseCard.actionUnpublish")
    : t("teacherDashboard.courseCard.actionPublish")

  return (
    // The whole card opens the course. A teacher on a phone tapped the
    // cover, the badge and the space beside the name — "Preaching Course - I
    // Published 4 lessons" in the session replay — and nothing answered; only
    // the letters of the name were a link. The name stays the one link (its
    // ::after stretches over the card), so a screen reader still hears one
    // link per course, and the controls sit above it on their own layer.
    <Card className="group lift relative transition-colors hover:border-brand/30">
      <div className="flex items-start gap-3 p-4 sm:gap-4 sm:p-5">
        {course.image_url ? (
          <img
            src={toProxyImage(course.image_url)}
            alt={t("teacherDashboard.courseCard.thumbnailAlt", { title: course.title })}
            loading="lazy"
            className="h-16 w-16 shrink-0 rounded-lg object-cover sm:h-20 sm:w-20"
          />
        ) : (
          <div className="h-16 w-16 shrink-0 overflow-hidden rounded-lg sm:h-20 sm:w-20">
            <CourseCoverFallback courseId={course.id} title={course.title} size="sm" />
          </div>
        )}
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
            {/* The name opens the course, as a name does everywhere else in
                the app; it was plain text, and the way in was an icon. */}
            {/* Its own line on a phone: beside «Опубликован» the name had
                a few letters and read «Де…». */}
            <h3 className="line-clamp-2 min-w-0 basis-full break-words text-base font-semibold sm:basis-0 sm:flex-1 sm:line-clamp-1 sm:text-lg">
              <Link
                to={`/teacher/courses/${course.id}`}
                className="underline-offset-4 transition-colors after:absolute after:inset-0 after:rounded-card hover:text-brand hover:underline focus-visible:outline-none focus-visible:after:ring-2 focus-visible:after:ring-brand"
              >
                {course.title}
              </Link>
            </h3>
            <Badge
              variant={isPublished ? "success" : isPublishing ? "warningSubtle" : "warning"}
              className="shrink-0"
            >
              {isPublished
                ? t("teacherDashboard.courseCard.statusPublished")
                : isPublishing
                  ? t("teacherDashboard.courseCard.statusPublishing")
                  : t("teacherDashboard.courseCard.statusDraft")}
            </Badge>
            {pendingGrading > 0 && (
              <Link
                to={`/teacher/courses/${course.id}/gradebook`}
                className="relative z-10 shrink-0 rounded-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2"
              >
                {/* The number on the dashboard header answers "do I owe anyone
                    anything today"; this answers "where". Without the link the
                    teacher still has to hunt for the course. */}
                <Badge variant="warningSubtle">
                  {t("teacherDashboard.courseCard.pendingGrading", { count: pendingGrading })}
                </Badge>
              </Link>
            )}
          </div>
          <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-ink-muted">
            <span className="flex items-center gap-1">
              <BookOpen className="h-4 w-4" strokeWidth={1.75} aria-hidden />
              {t("teacherDashboard.courseCard.lessons", { count: lessonCount })}
            </span>
            {/* Only for a course that groups its lessons. A module count of
                zero is not news to a teacher who never made one. */}
            {moduleCount > 0 && (
              <span className="flex items-center gap-1">
                <Layers className="h-4 w-4" strokeWidth={1.75} aria-hidden />
                {t("teacherDashboard.courseCard.modules", { count: moduleCount })}
              </span>
            )}
            {/* The students, one tap from the course on every width. On a phone
                they were the fourth item of the "…" menu, and that menu was the
                only way a teacher found them (RUM, 2026-09-20 and 2026-10-15). */}
            <Link
              to={`/teacher/courses/${course.id}/progress`}
              className="relative z-10 -my-2 inline-flex min-h-11 items-center gap-1 rounded-md font-medium text-ink underline underline-offset-4 transition-colors hover:text-brand focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand sm:min-h-0"
            >
              <Users className="h-4 w-4" strokeWidth={1.75} aria-hidden />
              {t("teacherDashboard.courseCard.students")}
            </Link>
          </div>
        </div>
        <div className="relative z-10 flex shrink-0 items-center gap-1">
          {/* Desktop: inline quick actions. Mobile: single overflow menu. */}
          <Link to={`/teacher/courses/${course.id}/analytics`} className="hidden sm:inline-flex">
            <Button
              variant="ghost"
              size="sm"
              title={t("teacherDashboard.courseCard.actionAnalytics")}
            >
              <BarChart3 className="h-4 w-4" strokeWidth={1.75} aria-hidden />
              <span className="sr-only">
                {t("teacherDashboard.courseCard.actionAnalytics")}
              </span>
            </Button>
          </Link>
          <Link to={`/teacher/courses/${course.id}/gradebook`} className="hidden sm:inline-flex">
            <Button
              variant="ghost"
              size="sm"
              title={t("teacherDashboard.courseCard.actionGradebook")}
            >
              <ClipboardList className="h-4 w-4" strokeWidth={1.75} aria-hidden />
              <span className="sr-only">
                {t("teacherDashboard.courseCard.actionGradebook")}
              </span>
            </Button>
          </Link>
          <Button
            variant="ghost"
            size="sm"
            className="hidden sm:inline-flex"
            title={togglePublishLabel}
            disabled={togglingId === course.id}
            onClick={() => onToggleStatus(course)}
          >
            {isOut ? (
              <EyeOff className="h-4 w-4" strokeWidth={1.75} aria-hidden />
            ) : (
              <Eye className="h-4 w-4" strokeWidth={1.75} aria-hidden />
            )}
            <span className="sr-only">{togglePublishLabel}</span>
          </Button>
          {/* No pencil: it opened the same editor the whole card opens, and on
              a phone its 36px broke «Preaching Course - I» onto two lines. */}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                variant="ghost"
                size="sm"
                className="h-11 w-11 p-0 sm:h-9 sm:w-9"
                aria-label={t("teacherDashboard.courseCard.actionMore")}
                title={t("teacherDashboard.courseCard.actionMore")}
              >
                <MoreHorizontal className="h-4 w-4" strokeWidth={1.75} aria-hidden />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="min-w-[14rem]">
              {/* Mobile-only mirror of the inline actions (editing is inline
                  on every width now). */}
              <DropdownMenuItem
                onSelect={() => onToggleStatus(course)}
                disabled={togglingId === course.id}
                className="sm:hidden"
              >
                {isOut ? (
                  <EyeOff className="h-4 w-4" strokeWidth={1.75} aria-hidden />
                ) : (
                  <Eye className="h-4 w-4" strokeWidth={1.75} aria-hidden />
                )}
                {togglePublishLabel}
              </DropdownMenuItem>
              <DropdownMenuItem asChild className="sm:hidden">
                <Link to={`/teacher/courses/${course.id}/analytics`}>
                  <BarChart3 className="h-4 w-4" strokeWidth={1.75} aria-hidden />
                  {t("teacherDashboard.courseCard.actionAnalytics")}
                </Link>
              </DropdownMenuItem>
              <DropdownMenuItem asChild className="sm:hidden">
                <Link to={`/teacher/courses/${course.id}/gradebook`}>
                  <ClipboardList className="h-4 w-4" strokeWidth={1.75} aria-hidden />
                  {t("teacherDashboard.courseCard.actionGradebook")}
                </Link>
              </DropdownMenuItem>
              <DropdownMenuSeparator className="sm:hidden" />
              <DropdownMenuItem
                onSelect={() => onClone(course.id)}
                disabled={cloningId === course.id}
              >
                {cloningId === course.id ? (
                  <Loader2 className="h-4 w-4 animate-spin" strokeWidth={1.75} aria-hidden />
                ) : (
                  <Copy className="h-4 w-4" strokeWidth={1.75} aria-hidden />
                )}
                {t("teacherDashboard.courseCard.actionClone")}
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem
                onSelect={() => onDelete(course.id)}
                className="text-destructive focus:text-destructive"
              >
                <Trash2 className="h-4 w-4" strokeWidth={1.75} aria-hidden />
                {t("teacherDashboard.courseCard.actionDelete")}
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>
    </Card>
  )
}
