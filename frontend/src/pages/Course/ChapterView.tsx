import { useEffect, useState, useCallback, useMemo, memo } from "react"
import { useTranslation } from "react-i18next"
import { useParams, Link, useNavigate } from "react-router-dom"
import { sanitizeHtml as sanitize } from "@/lib/sanitize"
import PageSpinner from "@/components/ui/PageSpinner"
import { Button } from "@/components/ui/button"
import { coursesService } from "@/services/courses"
import { storageService } from "@/services/storage"
import { toast } from "@/lib/toast"
import { useAuth } from "@/context/useAuth"
import type { Module, Chapter, ChapterBlock } from "@/types"
import {
  ArrowLeft,
  ArrowRight,
  Book,
  CheckCircle,
  Circle,
  Lock,
  Download,
  File,
  Loader2,
  RefreshCw,
} from "lucide-react"
import QuizTaker from "@/components/quiz/QuizTaker"
import AssignmentPanel from "@/components/assignment/AssignmentPanel"
import { PressFeedback } from "@/components/motion"
import {
  getChapterTypeMeta,
  isGradableChapterType,
  normalizeChapterType,
} from "@/lib/chapterTypes"
import { ErrorState } from "@/components/patterns"
import { useUserTour } from "@/hooks/useUserTour"
import { chapterViewSteps } from "@/lib/tourSteps"

const BlockRenderer = memo(function BlockRenderer({
  block,
  onProgressChanged,
  onAssignmentCountLoaded,
}: {
  block: ChapterBlock
  onProgressChanged?: () => void
  onAssignmentCountLoaded?: (count: number) => void
}) {
  const { t } = useTranslation()
  const sanitizedContent = useMemo(
    () => (block.content ? sanitize(block.content) : ""),
    [block.content],
  )

  switch (block.block_type) {
    case "text":
      return sanitizedContent ? (
        <div
          className="prose max-w-none"
          dangerouslySetInnerHTML={{ __html: sanitizedContent }}
        />
      ) : null

    case "quiz":
      return block.quiz_id ? (
        <QuizTaker chapterId={block.chapter_id} quizId={block.quiz_id} onSubmitted={onProgressChanged} />
      ) : null

    case "assignment":
      return block.assignment_id ? (
        <AssignmentPanel
          chapterId={block.chapter_id}
          assignmentId={block.assignment_id}
          onSubmitted={onProgressChanged}
          onCountLoaded={onAssignmentCountLoaded}
        />
      ) : null

    case "file":
      return block.file_bucket && block.file_path ? (
        <FileBlockLink
          bucket={block.file_bucket}
          path={block.file_path}
          label={block.file_name || block.content || t("chapter.downloadFile")}
        />
      ) : null

    default:
      return null
  }
})

function FileBlockLink({
  bucket,
  path,
  label,
}: {
  bucket: string
  path: string
  label: string
}) {
  const { t } = useTranslation()
  const [opening, setOpening] = useState(false)

  // Sign on click so the URL is always valid against the current Supabase
  // secret. Never store a pre-signed URL anywhere — doing so would
  // leak all historical signatures on every JWT rotation.
  const handleClick = useCallback(async () => {
    if (opening) return
    setOpening(true)
    try {
      const url = await storageService.getSignedBlockFileUrl(bucket, path)
      window.open(url, "_blank", "noopener,noreferrer")
    } catch {
      toast({ title: t("toast.openFileFailed"), variant: "destructive" })
    } finally {
      setOpening(false)
    }
  }, [bucket, path, opening, t])

  return (
    <button
      type="button"
      onClick={handleClick}
      disabled={opening}
      className="group flex w-full items-center gap-3 rounded-md border border-border bg-card px-4 py-3 text-left transition-colors hover:border-primary/40 hover:bg-muted/40 disabled:opacity-60"
      aria-label={t("chapter.downloadFileAria", { name: label })}
    >
      <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-muted">
        {opening ? (
          <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" strokeWidth={1.75} aria-hidden />
        ) : (
          <File className="h-4 w-4 text-muted-foreground" strokeWidth={1.75} aria-hidden />
        )}
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-xs font-medium uppercase tracking-[0.18em] text-muted-foreground">
          {t("chapter.attachmentEyebrow")}
        </p>
        <p className="mt-0.5 truncate text-sm font-medium text-foreground">{label}</p>
      </div>
      <Download className="h-4 w-4 shrink-0 text-muted-foreground transition-colors group-hover:text-primary" strokeWidth={1.75} aria-hidden />
    </button>
  )
}

/**
 * Renders the reading chapter body — loader, list of blocks, empty state.
 * Centralised so the page component stays declarative.
 */
function ChapterBodyBlocks({
  loading,
  blocks,
  loadError,
  onRetry,
  onProgressChanged,
  onAssignmentCountLoaded,
}: {
  loading: boolean
  blocks: ChapterBlock[]
  loadError: boolean
  onRetry: () => void
  onProgressChanged?: () => void
  onAssignmentCountLoaded?: (count: number) => void
}) {
  const { t } = useTranslation()
  if (loading) return <PageSpinner variant="section" />
  if (loadError) {
    // Reading a chapter whose blocks failed to load should NOT render
    // as "this chapter is empty" — that's how a teacher discovers a
    // network blip looks identical to deliberately empty content and
    // emails support thinking their content vanished.
    return (
      <ErrorState
        title={t("chapter.blocksLoadFailed")}
        description={t("chapter.blocksLoadFailedDescription")}
        action={
          <Button size="sm" onClick={onRetry}>
            <RefreshCw className="mr-1.5 h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
            {t("common.tryAgain")}
          </Button>
        }
      />
    )
  }
  if (blocks.length === 0) {
    return (
      <div className="rounded-md border border-dashed border-border bg-muted/20 px-6 py-12 text-center">
        <p className="text-sm text-muted-foreground">
          {t("chapter.emptyContent")}
        </p>
      </div>
    )
  }
  return (
    <div className="stagger-fade-in space-y-6">
      {blocks.map((block, idx) => (
        <div
          key={block.id}
          style={{ "--stagger-index": Math.min(idx, 12) } as React.CSSProperties}
        >
          <BlockRenderer
            block={block}
            onProgressChanged={onProgressChanged}
            onAssignmentCountLoaded={onAssignmentCountLoaded}
          />
        </div>
      ))}
    </div>
  )
}

function ChapterNavLink({
  side,
  chapter,
  courseId,
  moduleId,
  locked,
}: {
  side: "prev" | "next"
  chapter: Chapter | null
  courseId?: string
  moduleId?: string
  locked?: boolean
}) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const eyebrow = side === "prev" ? t("chapter.prevEyebrow") : t("chapter.nextEyebrow")
  const fallbackLabel = side === "prev" ? t("chapter.prevChapter") : t("chapter.nextChapter")
  const alignment = side === "prev" ? "text-left" : "text-right"
  const justify = side === "prev" ? "justify-start" : "justify-end"

  const disabledClass =
    "flex min-w-0 flex-1 cursor-not-allowed flex-col rounded-md border border-border bg-muted/20 px-3 py-2 opacity-60"
  const enabledClass =
    "group flex min-w-0 flex-1 flex-col rounded-md border border-border bg-card px-3 py-2 transition-colors hover:border-primary/40 hover:bg-muted/30"

  if (!chapter) {
    return (
      <div className={`${disabledClass} ${alignment}`} aria-hidden="true">
        <span className={`flex items-center gap-1.5 text-xs font-medium uppercase tracking-[0.18em] text-muted-foreground ${justify}`}>
          {side === "prev" && <ArrowLeft className="h-3.5 w-3.5" strokeWidth={1.75} />}
          {eyebrow}
          {side === "next" && <ArrowRight className="h-3.5 w-3.5" strokeWidth={1.75} />}
        </span>
        <span className="mt-0.5 truncate text-sm text-muted-foreground/70">
          {fallbackLabel}
        </span>
      </div>
    )
  }

  if (locked) {
    return (
      <div className={`${disabledClass} ${alignment}`} aria-label={fallbackLabel}>
        <span className={`flex items-center gap-1.5 text-xs font-medium uppercase tracking-[0.18em] text-muted-foreground ${justify}`}>
          <Lock className="h-3.5 w-3.5" strokeWidth={1.75} />
          {eyebrow}
        </span>
        <span className="mt-0.5 truncate text-sm font-medium text-muted-foreground">
          {chapter.title}
        </span>
      </div>
    )
  }

  return (
    <PressFeedback className="flex min-w-0 flex-1">
      <button
        type="button"
        onClick={() =>
          navigate(`/courses/${courseId}/modules/${moduleId}/chapters/${chapter.id}`)
        }
        className={`${enabledClass} ${alignment}`}
        aria-label={`${eyebrow}: ${chapter.title}`}
      >
        <span className={`flex items-center gap-1.5 text-xs font-medium uppercase tracking-[0.18em] text-muted-foreground transition-colors group-hover:text-primary ${justify}`}>
          {side === "prev" && <ArrowLeft className="h-3.5 w-3.5" strokeWidth={1.75} />}
          {eyebrow}
          {side === "next" && <ArrowRight className="h-3.5 w-3.5" strokeWidth={1.75} />}
        </span>
        <span className="mt-0.5 truncate text-sm font-medium text-foreground">
          {chapter.title}
        </span>
      </button>
    </PressFeedback>
  )
}

function ChapterNav({
  prevChapter,
  nextChapter,
  currentIdx,
  total,
  courseId,
  moduleId,
  isNextLocked,
}: {
  prevChapter: Chapter | null
  nextChapter: Chapter | null
  currentIdx: number
  total: number
  courseId?: string
  moduleId?: string
  isNextLocked: boolean
}) {
  const { t } = useTranslation()

  return (
    <nav
      aria-label={t("chapter.navAriaLabel")}
      className="mt-10 border-t border-border pt-6"
    >
      <p className="mb-3 text-center text-xs font-medium uppercase tracking-[0.18em] text-muted-foreground tabular-nums">
        {t("chapter.positionEyebrow", { current: currentIdx + 1, total })}
      </p>
      <div className="flex items-stretch gap-2 sm:gap-3">
        <ChapterNavLink
          side="prev"
          chapter={prevChapter}
          courseId={courseId}
          moduleId={moduleId}
        />
        <ChapterNavLink
          side="next"
          chapter={nextChapter}
          courseId={courseId}
          moduleId={moduleId}
          locked={isNextLocked}
        />
      </div>
    </nav>
  )
}

export default function ChapterView() {
  const { t, i18n } = useTranslation()
  const { courseId, moduleId, chapterId } = useParams<{
    courseId: string
    moduleId: string
    chapterId: string
  }>()
  const { user } = useAuth()

  const [mod, setMod] = useState<Module | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [completedIds, setCompletedIds] = useState<Set<string>>(new Set())
  const [chapterBlocks, setChapterBlocks] = useState<ChapterBlock[]>([])
  const [loadingBlocks, setLoadingBlocks] = useState(false)
  const [blocksLoadError, setBlocksLoadError] = useState(false)
  const [blocksReloadKey, setBlocksReloadKey] = useState(0)
  const retryBlocks = useCallback(() => {
    setBlocksReloadKey((k) => k + 1)
  }, [])
  const [hasAssignments, setHasAssignments] = useState(false)

  useUserTour({
    tourId: "chapter-view-v1",
    steps: chapterViewSteps(t),
    ready: !loading && !error && mod !== null,
  })

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
        const [m, completedChapterIds] = await Promise.all([
          coursesService.getModule(courseId, moduleId),
          coursesService.getMyChapterProgress(courseId).catch(() => [] as string[]),
        ])
        if (cancelled) return
        setMod(m)
        setCompletedIds(new Set(completedChapterIds))
      } catch {
        if (!cancelled) setError(t("errors.loadChapterFailed"))
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => { cancelled = true }
    // ``i18n.language`` so locale flip refreshes the localised module
    // title + chapter list. ``t`` is intentionally not a dep.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [courseId, moduleId, user?.id, i18n.language])

  const sortedChapters = useMemo(
    () => [...(mod?.chapters ?? [])].sort((a, b) => a.order_index - b.order_index),
    [mod],
  )

  const currentIdx = sortedChapters.findIndex((c) => c.id === chapterId)
  const chapter = currentIdx >= 0 ? sortedChapters[currentIdx] : null
  const prevChapter = currentIdx > 0 ? sortedChapters[currentIdx - 1] ?? null : null
  const nextChapter = currentIdx < sortedChapters.length - 1 ? sortedChapters[currentIdx + 1] ?? null : null

  useEffect(() => {
    if (!chapter) return
    let cancelled = false

    setHasAssignments(false)

    // Only reading chapters carry blocks; quiz/exam/assignment render their
    // own dedicated panels.
    if (normalizeChapterType(chapter.chapter_type) !== "reading") {
      setChapterBlocks([])
      return
    }

    setLoadingBlocks(true)
    setBlocksLoadError(false)
    coursesService
      .getChapterBlocks(chapter.id)
      .then((blocks) => {
        if (cancelled) return
        setChapterBlocks(blocks.sort((a, b) => a.order_index - b.order_index))
        setLoadingBlocks(false)
      })
      .catch(() => {
        if (cancelled) return
        // Don't ``catch(() => [])`` silently — a failed fetch renders
        // identically to a teacher-published-empty chapter and there's
        // no way for the reader to tell the difference. Track an
        // explicit error so ``ChapterBodyBlocks`` can surface a retry.
        setChapterBlocks([])
        setBlocksLoadError(true)
        setLoadingBlocks(false)
      })

    return () => { cancelled = true }
    // ``i18n.language`` so a locale flip mid-read re-pulls the
    // translated HTML for the same chapter — the chapter object
    // itself doesn't change, but its rendered content does. This was
    // the most visible "language switch doesn't update the page"
    // symptom: course title flipped, chapter body didn't.
    // ``blocksReloadKey`` lets the retry button re-run this effect
    // without a full route navigation.
  }, [chapter, i18n.language, blocksReloadKey])

  const isChapterLocked = useCallback(
    (ch: Chapter, idx: number) => {
      if (!ch.is_locked) return false
      if (idx === 0) return false
      const prev = sortedChapters[idx - 1]
      if (!prev || !isGradableChapterType(prev.chapter_type)) return false
      return !completedIds.has(prev.id)
    },
    [sortedChapters, completedIds],
  )

  const refreshCompletion = useCallback(async () => {
    if (!chapter || !courseId) return
    try {
      const completedChapterIds = await coursesService.getMyChapterProgress(courseId)
      setCompletedIds(new Set(completedChapterIds))
    } catch {
      // non-critical
    }
  }, [chapter, courseId])

  const handleAssignmentCountLoaded = useCallback((count: number) => {
    setHasAssignments((prev) => (count > 0 ? true : prev))
  }, [])

  if (loading) {
    return <PageSpinner />
  }

  if (error || !mod || !chapter) {
    return (
      <div className="container mx-auto px-4">
        <ErrorState
          icon={<Book strokeWidth={1.75} />}
          title={error ?? t("toast.chapterNotFound")}
          action={
            courseId && moduleId ? (
              <Link to={`/courses/${courseId}/modules/${moduleId}`}>
                <Button variant="outline" size="sm">{t("course.backToModule")}</Button>
              </Link>
            ) : (
              <Link to="/">
                <Button variant="outline" size="sm">{t("course.goHome")}</Button>
              </Link>
            )
          }
        />
      </div>
    )
  }

  const locked = isChapterLocked(chapter, currentIdx)
  const isCompleted = completedIds.has(chapter.id)

  if (locked) {
    return (
      <div className="container mx-auto px-4 py-6 max-w-3xl">
        <Link to={`/courses/${courseId}/modules/${moduleId}`} className="-mx-2 mb-4 inline-flex">
          <Button variant="ghost" size="sm" className="h-11 text-xs sm:h-8">
            <ArrowLeft className="mr-1.5 h-4 w-4" strokeWidth={1.75} aria-hidden />
            {t("course.backToModule")}
          </Button>
        </Link>

        <div className="text-center py-16">
          <Lock className="h-12 w-12 text-muted-foreground mx-auto mb-4" strokeWidth={1.75} />
          <h2 className="font-serif text-xl font-semibold mb-2">{t("chapter.lockedTitle")}</h2>
          <p className="text-muted-foreground">{t("chapter.lockedHint")}</p>
          {prevChapter && (
            <Link to={`/courses/${courseId}/modules/${moduleId}/chapters/${prevChapter.id}`}>
              <Button className="mt-4">{t("chapter.goToPreviousChapter")}</Button>
            </Link>
          )}
        </div>
      </div>
    )
  }

  const chapterType = normalizeChapterType(chapter.chapter_type)
  const chapterTypeMeta = getChapterTypeMeta(chapterType)
  const ChapterTypeIcon = chapterTypeMeta.icon

  return (
    <div className="container mx-auto px-4 py-6 max-w-3xl">
      <Link to={`/courses/${courseId}/modules/${moduleId}`} className="-mx-2 mb-6 inline-flex">
        <Button variant="ghost" size="sm" className="h-11 text-xs sm:h-8">
          <ArrowLeft className="mr-1.5 h-4 w-4" strokeWidth={1.75} aria-hidden />
          {t("course.backToModule")}
        </Button>
      </Link>

      <header data-tour="chapter-header" className="mb-10">
        <p className="mb-3 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs font-medium uppercase tracking-[0.18em] text-muted-foreground">
          <span className="inline-flex items-center gap-1.5">
            <ChapterTypeIcon className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
            {t(`chapterTypes.${chapterType}.label`)}
          </span>
          <span aria-hidden className="text-muted-foreground/40">·</span>
          <span className="tabular-nums">
            {t("chapter.positionEyebrow", { current: currentIdx + 1, total: sortedChapters.length })}
          </span>
          {mod.title && (
            <>
              <span aria-hidden className="text-muted-foreground/40">·</span>
              <span className="normal-case tracking-normal text-muted-foreground/80 text-wrap-safe">
                {mod.title}
              </span>
            </>
          )}
        </p>
        <h1 className="font-serif text-3xl font-semibold tracking-tight text-wrap-safe sm:text-4xl">
          {chapter.title}
        </h1>
      </header>

      <div data-tour="chapter-body" className="mb-10 space-y-6">
        {chapterType === "reading" && (
          <ChapterBodyBlocks
            loading={loadingBlocks}
            blocks={chapterBlocks}
            loadError={blocksLoadError}
            onRetry={retryBlocks}
            onProgressChanged={refreshCompletion}
            onAssignmentCountLoaded={handleAssignmentCountLoaded}
          />
        )}

        {(chapterType === "quiz" || chapterType === "exam") && (
          <QuizTaker chapterId={chapter.id} onSubmitted={refreshCompletion} />
        )}

        {chapterType === "assignment" && (
          <AssignmentPanel
            chapterId={chapter.id}
            onSubmitted={refreshCompletion}
            onCountLoaded={handleAssignmentCountLoaded}
          />
        )}
      </div>

      {hasAssignments && (
        <div className="mt-6 border-t border-border pt-5">
          {isCompleted ? (
            <p className="flex items-center gap-2 text-sm font-medium text-success">
              <CheckCircle className="h-4 w-4 shrink-0" strokeWidth={1.75} />
              {t("chapter.completed")}
            </p>
          ) : (
            <p className="flex items-center gap-2 text-sm text-muted-foreground">
              <Circle className="h-4 w-4 shrink-0" strokeWidth={1.75} />
              {t("chapter.submitAssignmentToComplete")}
            </p>
          )}
        </div>
      )}

      <div data-tour="chapter-nav">
        <ChapterNav
          prevChapter={prevChapter}
          nextChapter={nextChapter}
          currentIdx={currentIdx}
          total={sortedChapters.length}
          courseId={courseId}
          moduleId={moduleId}
          isNextLocked={nextChapter ? isChapterLocked(nextChapter, currentIdx + 1) : false}
        />
      </div>
    </div>
  )
}
