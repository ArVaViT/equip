import { Link } from "react-router-dom"
import { useTranslation } from "react-i18next"
import {
  AlertTriangle,
  ArrowRight,
  BookOpen,
  CheckCircle,
  Clock,
  Lock,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { StaggerChildren } from "@/components/motion"
import { isGradableChapterType } from "@/lib/chapterTypes"
import type { Module } from "@/types"
import { formatDate } from "./types"

interface Props {
  courseId: string
  modules: Module[]
  completedChapterIds: Set<string>
}

export function ModuleList({ courseId, modules, completedChapterIds }: Props) {
  const { t } = useTranslation()
  return (
    <div>
      <h2 className="text-lg font-semibold mb-3 flex items-center gap-2">
        <BookOpen className="h-4 w-4" strokeWidth={1.75} aria-hidden />
        {t("courseDetail.modulesHeading")}
        <span className="text-sm font-normal text-muted-foreground">({modules.length})</span>
      </h2>

      {modules.length > 0 ? (
        <StaggerChildren className="space-y-2">
          {modules.map((module, idx) => (
            <ModuleRow
              key={module.id}
              courseId={courseId}
              module={module}
              idx={idx}
              modules={modules}
              completedChapterIds={completedChapterIds}
            />
          ))}
        </StaggerChildren>
      ) : (
        <Card className="border-dashed">
          <CardContent className="py-8 text-center text-muted-foreground text-sm">
            {t("courseDetail.noModulesAddedYet")}
          </CardContent>
        </Card>
      )}
    </div>
  )
}

interface ModuleRowProps {
  courseId: string
  module: Module
  idx: number
  modules: Module[]
  completedChapterIds: Set<string>
}

function ModuleRow({
  courseId,
  module,
  idx,
  modules,
  completedChapterIds,
}: ModuleRowProps) {
  const { t } = useTranslation()
  const chapters = [...(module.chapters ?? [])].sort(
    (a, b) => a.order_index - b.order_index,
  )
  const gradable = chapters.filter((ch) => isGradableChapterType(ch.chapter_type))
  const gradableCount = gradable.length

  const isLocked = (() => {
    if (idx === 0) return false
    const prevModule = modules[idx - 1]
    if (!prevModule) return false
    const prevChapters = (prevModule.chapters ?? []).filter((ch) =>
      isGradableChapterType(ch.chapter_type),
    )
    if (prevChapters.length === 0) return false
    return !prevChapters.every((ch) => completedChapterIds.has(ch.id))
  })()

  const allComplete =
    gradableCount > 0 && gradable.every((ch) => completedChapterIds.has(ch.id))
  const completedInModule = gradable.filter((ch) => completedChapterIds.has(ch.id)).length

  return (
    <Card className={`group transition-colors ${isLocked ? "opacity-60" : "hover:border-primary/25"}`}>
      <CardHeader className="py-3 px-4">
        <div className="flex items-center justify-between gap-2">
          <CardTitle className="flex min-w-0 items-center gap-2 text-sm font-medium">
            <span
              className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs font-semibold ${
                isLocked
                  ? "bg-muted text-muted-foreground"
                  : allComplete
                    ? "bg-success/15 text-success"
                    : "bg-primary/10 text-primary"
              }`}
            >
              {isLocked ? (
                <Lock className="h-3 w-3" strokeWidth={1.75} aria-hidden />
              ) : allComplete ? (
                <CheckCircle className="h-3 w-3" strokeWidth={1.75} aria-hidden />
              ) : (
                idx + 1
              )}
            </span>
            <span className="min-w-0 flex-1 truncate">{module.title}</span>
            <span className="shrink-0 whitespace-nowrap text-xs font-normal text-muted-foreground">
              {gradableCount > 0
                ? `${completedInModule}/${gradableCount}`
                : `${chapters.length} ch.`}
            </span>
          </CardTitle>
          {!isLocked && (
            <Link to={`/courses/${courseId}/modules/${module.id}`}>
              <Button variant="ghost" size="sm" className="h-7 text-xs shrink-0">
                {t("courseDetail.openModule")}
                <ArrowRight className="ml-1 h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
              </Button>
            </Link>
          )}
          {isLocked && (
            <span className="text-xs text-muted-foreground flex items-center gap-1">
              <Lock className="h-3 w-3" strokeWidth={1.75} aria-hidden />
              {t("courseDetail.moduleLocked")}
            </span>
          )}
        </div>
        {isLocked && (
          <p className="text-xs text-muted-foreground ml-8 mt-1">
            {t("courseDetail.moduleLockHint")}
          </p>
        )}
        {module.description && (
          <CardDescription className="ml-8 mt-0.5 text-xs text-wrap-safe">
            {module.description}
          </CardDescription>
        )}
        {module.due_date && (() => {
          const dueDate = new Date(module.due_date)
          const now = new Date()
          const overdue = dueDate < now && !allComplete
          return (
            <div
              className={`ml-8 mt-1 flex items-center gap-1 text-[11px] ${
                overdue ? "text-destructive" : "text-muted-foreground"
              }`}
            >
              {overdue ? (
                <AlertTriangle className="h-3 w-3" strokeWidth={1.75} aria-hidden />
              ) : (
                <Clock className="h-3 w-3" strokeWidth={1.75} aria-hidden />
              )}
              <span>
                {overdue ? t("courseDetail.overdue") : t("courseDetail.due")}: {formatDate(module.due_date)}
              </span>
            </div>
          )
        })()}
      </CardHeader>
    </Card>
  )
}
