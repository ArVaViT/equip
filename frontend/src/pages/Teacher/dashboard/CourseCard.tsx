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
  Pencil,
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
import { toProxyImage } from "@/lib/images"
import { formatDate } from "@/i18n/format"
import type { Course } from "@/types"

interface Props {
  course: Course
  togglingId: string | null
  cloningId: string | null
  onToggleStatus: (course: Course) => void
  onClone: (id: string) => void
  onDelete: (id: string) => void
}

export function CourseCard({
  course,
  togglingId,
  cloningId,
  onToggleStatus,
  onClone,
  onDelete,
}: Props) {
  const { t } = useTranslation()
  const moduleCount = course.modules?.length ?? 0
  const isPublished = course.status === "published"
  const togglePublishLabel = isPublished
    ? t("teacherDashboard.courseCard.actionUnpublish")
    : t("teacherDashboard.courseCard.actionPublish")

  return (
    <Card className="group transition-colors hover:border-primary/30">
      <div className="flex items-start gap-3 p-4 sm:gap-4 sm:p-6">
        {course.image_url ? (
          <img
            src={toProxyImage(course.image_url)}
            alt={t("teacherDashboard.courseCard.thumbnailAlt", { title: course.title })}
            loading="lazy"
            className="h-16 w-16 shrink-0 rounded-lg object-cover sm:h-20 sm:w-20"
          />
        ) : (
          <div className="flex h-16 w-16 shrink-0 items-center justify-center rounded-lg bg-muted sm:h-20 sm:w-20">
            <BookOpen className="h-7 w-7 text-muted-foreground/40 sm:h-8 sm:w-8" strokeWidth={1.75} aria-hidden />
          </div>
        )}
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <h3 className="min-w-0 flex-1 truncate text-base font-semibold sm:text-lg">{course.title}</h3>
            <Badge variant={isPublished ? "success" : "warning"} className="shrink-0">
              {isPublished
                ? t("teacherDashboard.courseCard.statusPublished")
                : t("teacherDashboard.courseCard.statusDraft")}
            </Badge>
          </div>
          {course.description && (
            <p className="mt-1 line-clamp-2 text-sm text-muted-foreground">
              {course.description}
            </p>
          )}
          <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
            <span className="flex items-center gap-1">
              <Layers className="h-4 w-4" strokeWidth={1.75} aria-hidden />
              {t("teacherDashboard.courseCard.modules", { count: moduleCount })}
            </span>
            <span>
              {t("teacherDashboard.courseCard.createdOn", {
                date: formatDate(course.created_at),
              })}
            </span>
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-1">
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
          <Link to={`/teacher/courses/${course.id}/progress`} className="hidden sm:inline-flex">
            <Button
              variant="ghost"
              size="sm"
              title={t("teacherDashboard.courseCard.actionStudentProgress")}
            >
              <Users className="h-4 w-4" strokeWidth={1.75} aria-hidden />
              <span className="sr-only">
                {t("teacherDashboard.courseCard.actionStudentProgress")}
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
            {isPublished ? (
              <EyeOff className="h-4 w-4" strokeWidth={1.75} aria-hidden />
            ) : (
              <Eye className="h-4 w-4" strokeWidth={1.75} aria-hidden />
            )}
            <span className="sr-only">{togglePublishLabel}</span>
          </Button>
          <Link to={`/teacher/courses/${course.id}`} className="hidden sm:inline-flex">
            <Button
              variant="ghost"
              size="sm"
              aria-label={t("teacherDashboard.courseCard.actionEditCourse")}
              title={t("teacherDashboard.courseCard.actionEditCourse")}
            >
              <Pencil className="h-4 w-4" strokeWidth={1.75} aria-hidden />
            </Button>
          </Link>
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
              {/* Mobile-only mirror of the inline actions */}
              <DropdownMenuItem asChild className="sm:hidden">
                <Link to={`/teacher/courses/${course.id}`}>
                  <Pencil className="h-4 w-4" strokeWidth={1.75} aria-hidden />
                  {t("teacherDashboard.courseCard.actionEditCourse")}
                </Link>
              </DropdownMenuItem>
              <DropdownMenuItem
                onSelect={() => onToggleStatus(course)}
                disabled={togglingId === course.id}
                className="sm:hidden"
              >
                {isPublished ? (
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
              <DropdownMenuItem asChild className="sm:hidden">
                <Link to={`/teacher/courses/${course.id}/progress`}>
                  <Users className="h-4 w-4" strokeWidth={1.75} aria-hidden />
                  {t("teacherDashboard.courseCard.actionStudentProgress")}
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
