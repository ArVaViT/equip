import { useEffect, useState, useMemo } from "react"
import { useTranslation } from "react-i18next"
import { useParams, Link } from "react-router-dom"
import { formatDateTime } from "@/i18n/format"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { coursesService } from "@/services/courses"
import { useAuth } from "@/context/useAuth"
import type { Module } from "@/types"
import {
  ArrowLeft,
  Book,
  CheckCircle,
  Circle,
  ChevronRight,
  Lock,
  CalendarDays,
  AlertTriangle,
} from "lucide-react"
import { isGradableChapterType } from "@/lib/chapterTypes"
import ChapterTypeBadge from "@/components/course/ChapterTypeBadge"
import { ErrorState } from "@/components/patterns"
import { Skeleton } from "@/components/ui/skeleton"

export default function ModuleView() {
  const { t } = useTranslation()
  const { courseId, moduleId } = useParams<{ courseId: string; moduleId: string }>()
  const { user } = useAuth()
  const [module, setModule] = useState<Module | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [completedIds, setCompletedIds] = useState<Set<string>>(new Set())

  useEffect(() => {
    let cancelled = false
    const load = async () => {
      if (!courseId || !moduleId) {
        setLoading(false)
        setError(t("errors.invalidCourseLink"))
        return
      }
      setLoading(true)
      setError(null)
      try {
        const [mod, completedChapterIds] = await Promise.all([
          coursesService.getModule(courseId, moduleId),
          coursesService.getMyChapterProgress(courseId).catch(() => [] as string[]),
        ])
        if (cancelled) return
        setModule(mod)
        setCompletedIds(new Set(completedChapterIds))
      } catch {
        if (!cancelled) setError(t("errors.loadModuleFailed"))
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => { cancelled = true }
  }, [courseId, moduleId, user?.id, t])

  const sortedChapters = useMemo(
    () => [...(module?.chapters ?? [])].sort((a, b) => a.order_index - b.order_index),
    [module],
  )

  const gradableChapters = sortedChapters.filter((c) => isGradableChapterType(c.chapter_type))
  const allComplete = gradableChapters.length > 0 && gradableChapters.every((c) => completedIds.has(c.id))

  if (loading) {
    return (
      <div className="container mx-auto px-4 py-6 max-w-3xl">
        <Skeleton className="h-8 w-28 mb-4" />
        <div className="mb-4 space-y-2">
          <Skeleton className="h-7 w-2/3" />
          <Skeleton className="h-4 w-full" />
        </div>
        <Skeleton className="h-2 w-full rounded-full mb-4" />
        <div className="space-y-3">
          {[1, 2, 3, 4].map((i) => (
            <Skeleton key={i} className="h-14 rounded-lg" />
          ))}
        </div>
      </div>
    )
  }

  if (error || !module) {
    return (
      <div className="container mx-auto px-4">
        <ErrorState
          icon={<Book strokeWidth={1.75} />}
          title={error ?? t("toast.moduleNotFound")}
          action={
            <Link to={courseId ? `/courses/${courseId}` : "/"}>
              <Button variant="outline" size="sm">{t("course.backToCourse")}</Button>
            </Link>
          }
        />
      </div>
    )
  }

  const completedCount = gradableChapters.filter((c) => completedIds.has(c.id)).length
  const progressPercent = gradableChapters.length > 0 ? Math.round((completedCount / gradableChapters.length) * 100) : 100

  return (
    <div className="container mx-auto px-4 py-6 max-w-3xl">
      <Link to={`/courses/${courseId}`}>
        <Button variant="ghost" size="sm" className="mb-4 h-8 text-xs">
          <ArrowLeft className="h-3.5 w-3.5 mr-1.5" strokeWidth={1.75} />
          {t("course.backToCourse")}
        </Button>
      </Link>

      <div className="mb-4">
        <h1 className="mb-1 text-2xl font-bold tracking-tight text-wrap-safe">{module.title}</h1>
        {module.description && (
          <p className="text-sm leading-relaxed text-muted-foreground text-wrap-safe whitespace-pre-line">
            {module.description}
          </p>
        )}
      </div>

      {module.due_date && (() => {
        const dueDate = new Date(module.due_date)
        const now = new Date()
        const isOverdue = dueDate < now && !allComplete
        const isUpcoming = !isOverdue && dueDate.getTime() - now.getTime() < 3 * 24 * 60 * 60 * 1000
        return (
          <div className={`mb-4 flex items-center gap-2 rounded-md border px-3 py-2 ${
            isOverdue
              ? "border-l-[3px] border-l-destructive border-border bg-destructive/5"
              : isUpcoming
                ? "border-l-[3px] border-l-warning border-border bg-warning/10"
                : "border-border bg-muted/50"
          }`}>
            {isOverdue ? (
              <AlertTriangle className="h-4 w-4 shrink-0 text-destructive" strokeWidth={1.75} />
            ) : (
              <CalendarDays className="h-4 w-4 shrink-0 text-muted-foreground" strokeWidth={1.75} />
            )}
            <span className={`text-sm font-medium ${
              isOverdue ? "text-destructive" : isUpcoming ? "text-warning" : "text-foreground"
            }`}>
              {isOverdue ? t("module.overdue") : t("module.due")}:{" "}
              {formatDateTime(dueDate, {
                weekday: "short",
                month: "short",
                day: "numeric",
                year: "numeric",
                hour: "2-digit",
                minute: "2-digit",
              })}
            </span>
          </div>
        )
      })()}

      {allComplete && (
        <div className="mb-4 flex items-center gap-2 rounded-md border border-border border-l-[3px] border-l-success bg-success/10 px-3 py-2">
          <CheckCircle className="h-4 w-4 shrink-0 text-success" strokeWidth={1.75} />
          <span className="text-sm font-medium text-success">{t("module.moduleComplete")}</span>
        </div>
      )}

      {gradableChapters.length > 0 && (
        <div className="mb-4">
          <div className="flex items-center justify-between text-xs mb-1">
            <span className="font-medium">
              {t("module.completedProgress", { done: completedCount, total: gradableChapters.length })}
            </span>
            <span className="text-muted-foreground">{progressPercent}%</span>
          </div>
          <div className="h-2 w-full rounded-full bg-muted overflow-hidden">
            <div
              className="h-full rounded-full bg-primary transition-all duration-500 ease-out"
              style={{ width: `${progressPercent}%` }}
            />
          </div>
        </div>
      )}

      <div>
        <h2 className="text-lg font-semibold mb-3 flex items-center gap-2">
          <Book className="h-4 w-4" strokeWidth={1.75} />
          {t("module.chaptersHeading")}
          <span className="text-sm font-normal text-muted-foreground">
            ({sortedChapters.length})
          </span>
        </h2>

        {sortedChapters.length > 0 ? (
          <div className="space-y-3">
            {sortedChapters.map((chapter, idx) => {
              const isGradable = isGradableChapterType(chapter.chapter_type)
              const isCompleted = isGradable && completedIds.has(chapter.id)
              const requiresTeacher = chapter.requires_completion
              const prevChapter = idx > 0 ? sortedChapters[idx - 1] : null
              const prevIsGradable = prevChapter ? isGradableChapterType(prevChapter.chapter_type) : false
              const isLocked = chapter.is_locked && prevChapter != null && prevIsGradable && !completedIds.has(prevChapter.id)

              if (isLocked) {
                return (
                  <Card
                    key={chapter.id}
                    className="animate-fade-in opacity-60 cursor-not-allowed"
                    style={{ animationDelay: `${idx * 50}ms` }}
                  >
                    <CardHeader className="pb-2">
                      <CardTitle className="flex min-w-0 items-center gap-2 text-base">
                        <Lock className="h-5 w-5 text-muted-foreground/50 shrink-0" strokeWidth={1.75} />
                        <span className="min-w-0 flex-1 truncate text-muted-foreground">
                          {chapter.title}
                        </span>
                        {chapter.chapter_type && (
                          <ChapterTypeBadge type={chapter.chapter_type} size="sm" />
                        )}
                        <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground/30" strokeWidth={1.75} />
                      </CardTitle>
                    </CardHeader>
                  </Card>
                )
              }

              return (
                <Link
                  key={chapter.id}
                  to={`/courses/${courseId}/modules/${moduleId}/chapters/${chapter.id}`}
                  className="block"
                >
                  <Card
                    className={`animate-fade-in transition-colors hover:border-primary/40 ${isCompleted ? "border-success/40 bg-success/5" : ""}`}
                    style={{ animationDelay: `${idx * 50}ms` }}
                  >
                    <CardHeader className="pb-2">
                      <CardTitle className="flex min-w-0 items-center gap-2 text-base">
                        {isGradable ? (
                          isCompleted ? (
                            <CheckCircle className="h-5 w-5 shrink-0 text-success" strokeWidth={1.75} />
                          ) : requiresTeacher ? (
                            <Lock className="h-5 w-5 shrink-0 text-warning" strokeWidth={1.75} />
                          ) : (
                            <Circle className="h-5 w-5 shrink-0 text-muted-foreground/40" strokeWidth={1.75} />
                          )
                        ) : null}
                        <span className={`min-w-0 flex-1 truncate ${isCompleted ? "text-muted-foreground" : ""}`}>
                          {chapter.title}
                        </span>
                        {chapter.chapter_type && (
                          <ChapterTypeBadge type={chapter.chapter_type} size="sm" />
                        )}
                        <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground/40" strokeWidth={1.75} />
                      </CardTitle>
                    </CardHeader>
                  </Card>
                </Link>
              )
            })}
          </div>
        ) : (
          <Card className="border-dashed">
            <CardContent className="py-12 text-center text-muted-foreground text-sm">
              {t("module.noChaptersYet")}
            </CardContent>
          </Card>
        )}
      </div>

    </div>
  )
}
