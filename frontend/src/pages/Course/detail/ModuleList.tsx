import { memo } from "react"
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
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { EmptyState } from "@/components/patterns"
import { StaggerChildren } from "@/components/motion"
import { isGradableChapterType } from "@/lib/chapterTypes"
import type { Module } from "@/types"
import { formatDate } from "./types"
import { isModuleLocked } from "../moduleProgress"
import { orNotTranslated } from "@/lib/untranslated"

interface Props {
  courseId: string
  modules: Module[]
  /** `null` when the progress request failed. See `moduleProgress.ts`. */
  completedChapterIds: Set<string> | null
}

export function ModuleList({ courseId, modules, completedChapterIds }: Props) {
  // Which row gets to explain the rule. Computed here rather than in the row,
  // because "am I the first locked one" is a fact about the list.
  const firstLockedIdx = modules.findIndex((_, idx) => {
    if (idx === 0) return false
    const prev = modules[idx - 1]
    if (!prev) return false
    const prevGradable = (prev.chapters ?? []).filter((ch) =>
      isGradableChapterType(ch.chapter_type),
    )
    return isModuleLocked(
      completedChapterIds,
      prevGradable.map((ch) => ch.id),
    )
  })
  const { t } = useTranslation()
  return (
    <div>
      <h2 className="mb-3 flex items-center gap-2 font-serif text-lg font-semibold tracking-tight">
        <BookOpen className="h-4 w-4" strokeWidth={1.75} aria-hidden />
        {t("courseDetail.modulesHeading")}
        <span className="text-sm font-normal text-ink-muted">({modules.length})</span>
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
              isFirstLocked={idx === firstLockedIdx}
            />
          ))}
        </StaggerChildren>
      ) : (
        <EmptyState
          icon={<BookOpen strokeWidth={1.75} aria-hidden />}
          title={t("courseDetail.noModulesAddedYet")}
          description={t("courseDetail.noModulesAddedYetDescription")}
        />
      )}
    </div>
  )
}

interface ModuleRowProps {
  courseId: string
  module: Module
  idx: number
  /** The first locked row is the only one that explains the rule. */
  isFirstLocked?: boolean
  modules: Module[]
  /** `null` when the progress request failed. See `moduleProgress.ts`. */
  completedChapterIds: Set<string> | null
}

const ModuleRow = memo(function ModuleRow({
  courseId,
  module,
  idx,
  isFirstLocked = false,
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
    return isModuleLocked(
      completedChapterIds,
      prevChapters.map((ch) => ch.id),
    )
  })()

  const allComplete =
    completedChapterIds !== null &&
    gradableCount > 0 &&
    gradable.every((ch) => completedChapterIds.has(ch.id))
  const completedInModule =
    completedChapterIds === null
      ? 0
      : gradable.filter((ch) => completedChapterIds.has(ch.id)).length

  return (
    <Card className={`group transition-colors ${isLocked ? "opacity-60" : "hover:border-brand/25"}`}>
      <CardHeader className="py-3 px-4">
        <div className="flex items-center justify-between gap-2">
          <CardTitle className="flex min-w-0 items-center gap-2 text-sm">
            <span
              className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs font-semibold ${
                isLocked
                  ? "bg-muted text-ink-muted"
                  : allComplete
                    ? "bg-success/15 text-success-ink"
                    : "bg-brand/10 text-brand-ink"
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
            <span className="min-w-0 flex-1 truncate">{orNotTranslated(t, module.title)}</span>
            <span className="shrink-0 whitespace-nowrap text-xs font-normal text-ink-muted">
              {gradableCount > 0
                ? `${completedInModule}/${gradableCount}`
                : `${chapters.length} ch.`}
            </span>
          </CardTitle>
          {!isLocked && (
            <Link
              to={`/courses/${courseId}/modules/${module.id}`}
              className="-my-2 inline-flex shrink-0 sm:my-0"
            >
              <Button variant="ghost" size="sm" className="h-11 text-xs sm:h-7">
                {t("courseDetail.openModule")}
                <ArrowRight className="ml-1 h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
              </Button>
            </Link>
          )}
          {isLocked && (
            <span className="text-xs text-ink-muted flex items-center gap-1">
              <Lock className="h-3 w-3" strokeWidth={1.75} aria-hidden />
              {t("courseDetail.moduleLocked")}
            </span>
          )}
        </div>
        {/* Only on the first locked row. A course with six modules and five
            walls repeated this identical sentence five times down the page,
            which reads as nagging rather than explaining — the rule is one
            rule, and it is stated once, next to the first door it applies
            to. The rest keep their «Locked» badge, which is the fact. */}
        {isLocked && isFirstLocked && (
          <p className="text-xs text-ink-muted ml-8 mt-1">
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
              className={`ml-8 mt-1 flex items-center gap-1 text-xs ${
                overdue ? "text-destructive" : "text-ink-muted"
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
})
