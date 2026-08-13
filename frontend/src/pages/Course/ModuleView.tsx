import { useMemo } from "react"
import { useTranslation } from "react-i18next"
import { useParams, Link } from "react-router-dom"
import { formatDateLong } from "@/i18n/format"
import { Card, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { coursesService } from "@/services/courses"
import { useAuth } from "@/context/useAuth"
import { useAsyncData } from "@/hooks/useAsyncData"
import type { Module } from "@/types"
import {
  ArrowLeft,
  Book,
  Check,
  CheckCircle,
  Circle,
  ChevronRight,
  Lock,
  CalendarDays,
  AlertTriangle,
} from "lucide-react"
import { isGradableChapterType } from "@/lib/chapterTypes"
import ChapterTypeBadge from "@/components/course/ChapterTypeBadge"
import { EmptyState, ErrorState } from "@/components/patterns"
import { Skeleton } from "@/components/ui/skeleton"
import { isChapterComplete, isChapterLocked, isChapterRead } from "./moduleProgress"

// Module ID + course ID come from the route, locale from i18n; bundle the
// fetcher's deps in one tuple so useAsyncData re-runs at the right edges.
interface ModuleFetchResult {
  module: Module | null
  /** `null` when the progress request failed — not the same as "none". */
  completedIds: Set<string> | null
  invalidLink: boolean
}

export default function ModuleView() {
  const { t, i18n } = useTranslation()
  const { courseId, moduleId } = useParams<{ courseId: string; moduleId: string }>()
  const { user } = useAuth()

  const { data, loading, error: fetchError } = useAsyncData<ModuleFetchResult>(
    async (isCancelled) => {
      if (!courseId || !moduleId) {
        return { module: null, completedIds: null, invalidLink: true }
      }
      const [mod, completedChapterIds] = await Promise.all([
        coursesService.getModule(courseId, moduleId),
        // `null`, not `[]`. An empty list means the student has finished
        // nothing; a failed request means we do not know. Rendering the second
        // as the first shows somebody who completed this module a page of
        // empty circles and a count of zero — see the note on `completedIds`.
        coursesService.getMyChapterProgress(courseId).catch(() => null),
      ])
      if (isCancelled()) {
        return { module: null, completedIds: null, invalidLink: false }
      }
      return {
        module: mod,
        completedIds: completedChapterIds === null ? null : new Set(completedChapterIds),
        invalidLink: false,
      }
    },
    // ``i18n.language`` so a locale flip re-pulls the localised module
    // title / chapter list. ``user?.id`` so a sign-in/sign-out re-pulls
    // the progress overlay.
    [courseId, moduleId, user?.id, i18n.language],
  )

  // Localised error string resolved at render time — using a token key
  // instead of storing the localised text means a locale flip while an
  // error is on screen updates the message without a refetch.
  const error: string | null = data?.invalidLink
    ? t("errors.invalidCourseLink")
    : fetchError
      ? t("errors.loadModuleFailed")
      : null
  const module = data?.module ?? null
  /**
   * `null` means the progress request failed, and every consumer below has to
   * say so rather than guess. The guess this replaces was that a failed fetch
   * meant "nothing completed": a student who had finished the module saw empty
   * circles, a count of zero, and no completion affordance.
   */
  const completedIds = data?.completedIds ?? null
  const progressKnown = completedIds !== null

  const sortedChapters = useMemo(
    () => [...(module?.chapters ?? [])].sort((a, b) => a.order_index - b.order_index),
    [module],
  )

  const gradableChapters = sortedChapters.filter((c) => isGradableChapterType(c.chapter_type))
  const allComplete =
    progressKnown && gradableChapters.length > 0 && gradableChapters.every((c) => completedIds.has(c.id))

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
          icon={<Book strokeWidth={1.75} aria-hidden />}
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

  const completedCount = progressKnown
    ? gradableChapters.filter((c) => completedIds.has(c.id)).length
    : 0
  const progressPercent = gradableChapters.length > 0 ? Math.round((completedCount / gradableChapters.length) * 100) : 100

  return (
    <div className="container mx-auto px-4 py-6 max-w-3xl">
      <Link to={`/courses/${courseId}`}>
        <Button variant="ghost" size="sm" className="mb-4 h-8 text-xs">
          <ArrowLeft className="h-3.5 w-3.5 mr-1.5" strokeWidth={1.75} aria-hidden />
          {t("course.backToCourse")}
        </Button>
      </Link>

      {/* Said out loud, not left to be inferred from a page of empty circles.
          A student who finished this module and meets a blank one needs to
          know the page is wrong, not conclude their work is gone. */}
      {!progressKnown && (
        <p role="status" className="mb-4 rounded-md border border-warning/30 bg-warning/10 px-3 py-2 text-sm text-warning-ink">
          {t("module.progressUnknown")}
        </p>
      )}

      <div className="mb-4">
        <h1 className="mb-1 font-serif text-2xl font-bold tracking-tight text-wrap-safe">{module.title}</h1>
        {module.description && (
          <p className="text-sm leading-relaxed text-ink-muted text-wrap-safe whitespace-pre-line">
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
              ? "border-l-stripe border-l-destructive border-edge bg-destructive/5"
              : isUpcoming
                ? "border-l-stripe border-l-warning border-edge bg-warning/10"
                : "border-edge bg-muted/50"
          }`}>
            {isOverdue ? (
              <AlertTriangle className="h-4 w-4 shrink-0 text-destructive" strokeWidth={1.75} aria-hidden />
            ) : (
              <CalendarDays className="h-4 w-4 shrink-0 text-ink-muted" strokeWidth={1.75} aria-hidden />
            )}
            <span className={`text-sm font-medium ${
              isOverdue ? "text-destructive" : isUpcoming ? "text-warning" : "text-ink"
            }`}>
              {isOverdue ? t("module.overdue") : t("module.due")}:{" "}
              {formatDateLong(dueDate, {
                weekday: "short",
                month: "short",
                hour: "2-digit",
                minute: "2-digit",
              })}
            </span>
          </div>
        )
      })()}

      {allComplete && (
        <div className="mb-4 flex items-center gap-2 rounded-md border-l-stripe border-l-success bg-success/10 px-3 py-2">
          <CheckCircle className="h-4 w-4 shrink-0 text-success-ink" strokeWidth={1.75} aria-hidden />
          <span className="text-sm font-medium text-success-ink">{t("module.moduleComplete")}</span>
        </div>
      )}

      {gradableChapters.length > 0 && (
        <div className="mb-4">
          <div className="flex items-center justify-between text-xs mb-1">
            <span className="font-medium">
              {/* Names what it counts. It used to read «0/1 completed» above a
                  list of three chapters — the two lessons are not gradable, so
                  they are not in the denominator, and a student had no way to
                  know that from the number. */}
              {t("module.completedProgress", { done: completedCount, total: gradableChapters.length })}
            </span>
            <span className="text-ink-muted">{progressPercent}%</span>
          </div>
          <div className="h-2 w-full rounded-full bg-muted overflow-hidden">
            <div
              className="h-full rounded-full bg-brand transition-all duration-500 ease-out"
              style={{ width: `${progressPercent}%` }}
            />
          </div>
        </div>
      )}

      <div>
        <h2 className="mb-3 flex items-center gap-2 font-serif text-lg font-semibold tracking-tight">
          <Book className="h-4 w-4" strokeWidth={1.75} aria-hidden />
          {t("module.chaptersHeading")}
          <span className="text-sm font-normal text-ink-muted">
            ({sortedChapters.length})
          </span>
        </h2>

        {sortedChapters.length > 0 ? (
          <div className="space-y-3">
            {sortedChapters.map((chapter, idx) => {
              const isGradable = isGradableChapterType(chapter.chapter_type)
              const isCompleted = isChapterComplete(completedIds, chapter, isGradable)
              const requiresTeacher = chapter.requires_completion
              const prevChapter = idx > 0 ? sortedChapters[idx - 1] : null
              const prevIsGradable = prevChapter ? isGradableChapterType(prevChapter.chapter_type) : false
              // Fails **open** when progress is unknown, and that direction is
              // deliberate. `!completedIds.has(...)` on a failed fetch is
              // `true`, so the old code locked every gated chapter — a student
              // who had earned their way through found a wall because a
              // request timed out. The server gates this for real; guessing on
              // the client can only be wrong in one of two directions, and
              // wrongly denying somebody their own progress is the worse one.
              const isLocked = isChapterLocked(completedIds, chapter, prevChapter ?? null, prevIsGradable)
              const isRead = isChapterRead(completedIds, chapter, isGradable)

              if (isLocked) {
                return (
                  <Card
                    key={chapter.id}
                    className="animate-fade-in opacity-60 cursor-not-allowed"
                    style={{ animationDelay: `${idx * 50}ms` }}
                  >
                    <CardHeader className="pb-2">
                      <CardTitle className="flex min-w-0 items-center gap-2 text-base">
                        <Lock className="h-5 w-5 text-ink-muted shrink-0" strokeWidth={1.75} aria-hidden />
                        <span className="min-w-0 flex-1 truncate text-ink-muted">
                          {chapter.title}
                        </span>
                        {chapter.chapter_type && (
                          <ChapterTypeBadge type={chapter.chapter_type} size="sm" />
                        )}
                        <ChevronRight className="h-4 w-4 shrink-0 text-ink-muted" strokeWidth={1.75} aria-hidden />
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
                    className={`animate-fade-in transition-colors hover:border-brand/40 ${isCompleted ? "border-success/40 bg-success/5" : ""}`}
                    style={{ animationDelay: `${idx * 50}ms` }}
                  >
                    <CardHeader className="pb-2">
                      <CardTitle className="flex min-w-0 items-center gap-2 text-base">
                        {isGradable ? (
                          isCompleted ? (
                            <CheckCircle className="h-5 w-5 shrink-0 text-success" strokeWidth={1.75} aria-hidden />
                          ) : requiresTeacher ? (
                            <Lock className="h-5 w-5 shrink-0 text-warning" strokeWidth={1.75} aria-hidden />
                          ) : (
                            <Circle className="h-5 w-5 shrink-0 text-ink-muted" strokeWidth={1.75} aria-hidden />
                          )
                        ) : isRead ? (
                          // Quieter than the assessment tick, and a different
                          // glyph: read is not passed. Before this the row drew
                          // nothing at all for a lesson, so marking one read
                          // left no trace anywhere and the control looked dead.
                          <Check
                            className="h-5 w-5 shrink-0 text-ink-muted"
                            strokeWidth={1.75}
                            aria-label={t("module.chapterRead")}
                          />
                        ) : null}
                        <span className={`min-w-0 flex-1 truncate ${isCompleted ? "text-ink-muted" : ""}`}>
                          {chapter.title}
                        </span>
                        {chapter.chapter_type && (
                          <ChapterTypeBadge type={chapter.chapter_type} size="sm" />
                        )}
                        <ChevronRight className="h-4 w-4 shrink-0 text-ink-muted" strokeWidth={1.75} aria-hidden />
                      </CardTitle>
                    </CardHeader>
                  </Card>
                </Link>
              )
            })}
          </div>
        ) : (
          <EmptyState
            icon={<Book strokeWidth={1.75} aria-hidden />}
            title={t("module.noChaptersYet")}
          />
        )}
      </div>

    </div>
  )
}
