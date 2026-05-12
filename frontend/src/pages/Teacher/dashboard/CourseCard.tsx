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
      <div className="flex items-start gap-4 p-6">
        {course.image_url ? (
          <img
            src={toProxyImage(course.image_url)}
            alt={t("teacherDashboard.courseCard.thumbnailAlt", { title: course.title })}
            loading="lazy"
            className="w-20 h-20 rounded-lg object-cover shrink-0"
          />
        ) : (
          <div className="w-20 h-20 rounded-lg bg-muted flex items-center justify-center shrink-0">
            <BookOpen className="h-8 w-8 text-muted-foreground/40" strokeWidth={1.75} aria-hidden />
          </div>
        )}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <h3 className="font-semibold text-lg truncate">{course.title}</h3>
            <Badge variant={isPublished ? "success" : "warning"}>
              {isPublished
                ? t("teacherDashboard.courseCard.statusPublished")
                : t("teacherDashboard.courseCard.statusDraft")}
            </Badge>
          </div>
          {course.description && (
            <p className="text-sm text-muted-foreground line-clamp-2 mt-1">
              {course.description}
            </p>
          )}
          <div className="flex items-center gap-4 mt-3 text-xs text-muted-foreground">
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
        <div className="flex items-center gap-1 shrink-0">
          <Link to={`/teacher/courses/${course.id}/analytics`}>
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
          <Link to={`/teacher/courses/${course.id}/gradebook`}>
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
          <Link to={`/teacher/courses/${course.id}/progress`}>
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
          <Link to={`/teacher/courses/${course.id}`}>
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
                aria-label={t("teacherDashboard.courseCard.actionMore")}
                title={t("teacherDashboard.courseCard.actionMore")}
              >
                <MoreHorizontal className="h-4 w-4" strokeWidth={1.75} aria-hidden />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem
                onSelect={() => onClone(course.id)}
                disabled={cloningId === course.id}
              >
                {cloningId === course.id ? (
                  <div className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" />
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
