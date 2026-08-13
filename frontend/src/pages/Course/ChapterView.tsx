import { useEffect, useRef, useState, useCallback, useMemo, memo } from "react"
import { useTranslation } from "react-i18next"
import { useParams, Link, useNavigate } from "react-router-dom"
import { sanitizeHtml as sanitize } from "@/lib/sanitize"
import { renderMathIn } from "@/lib/katex-render"
import { renderToggleCalloutsIn } from "@/lib/callout-toggle"
import { attachCopyButtonsIn } from "@/lib/codeblock-copy"
import { ImageLightbox } from "@/components/chapter/ImageLightbox"
import PageSpinner from "@/components/ui/PageSpinner"
import { Button } from "@/components/ui/button"
import { coursesService } from "@/services/courses"
import { progressService } from "@/services/progress"
import { storageService } from "@/services/storage"
import { toast } from "@/lib/toast"
import { useAuth } from "@/context/useAuth"
import type { Course, Module, Chapter, ChapterBlock } from "@/types"
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
  CHAPTER_TYPE_LABEL_KEYS,
  getChapterTypeMeta,
  isGradableChapterType,
  normalizeChapterType,
} from "@/lib/chapterTypes"
import { ErrorState } from "@/components/patterns"
import { useUserTour } from "@/hooks/useUserTour"
import { chapterViewSteps } from "@/lib/tourSteps"
import { recordCourseView } from "@/lib/recentlyViewed"

/**
 * Renders a sanitised text-block via ``dangerouslySetInnerHTML`` and
 * runs KaTeX over any ``<span data-type="inlineMath">`` markers the
 * math extension stored in the source. Lives outside BlockRenderer so
 * the ``useRef`` + ``useEffect`` for the post-render KaTeX pass have
 * a stable host element to anchor against.
 */
function TextBlockRender({ html }: { html: string }) {
  const { t } = useTranslation()
  const ref = useRef<HTMLDivElement>(null)
  // Image-lightbox state — the rendered chapter HTML is injected via
  // ``dangerouslySetInnerHTML`` so we can't attach React onClick to
  // each ``<img>``. Instead, delegate clicks at the wrapper div and
  // open the lightbox with the clicked image's src + alt.
  const [lightbox, setLightbox] = useState<{ src: string; alt: string } | null>(null)
  useEffect(() => {
    // Order matters: ``renderToggleCalloutsIn`` rewrites parent
    // elements (``div[data-callout="toggle"]`` → ``<details>``), so
    // run it before KaTeX touches descendant spans. Running KaTeX
    // first would still work — the rewrite copies child nodes into
    // ``<summary>`` and the rendered spans go along intact — but
    // toggle-first avoids extra DOM churn.
    renderToggleCalloutsIn(ref.current)
    // Async fire-and-forget: KaTeX (and its stylesheet) load lazily and
    // only when the chapter actually contains math markers. Copy-button
    // wiring below doesn't depend on math rendering, so no need to await.
    void renderMathIn(ref.current)
    attachCopyButtonsIn(ref.current, {
      copy: t("blockEditor.codeBlock.copy"),
      copied: t("blockEditor.codeBlock.copied"),
      ariaLabel: t("blockEditor.codeBlock.copyAriaLabel"),
    })
  }, [html, t])

  const handleClick = (e: React.MouseEvent<HTMLDivElement>) => {
    const target = e.target as HTMLElement
    if (target.tagName !== "IMG") return
    const img = target as HTMLImageElement
    // Skip tiny / decorative images (icons, small thumbs inside a
    // callout, an inline 16px badge): they shouldn't open a
    // fullscreen modal that hides surrounding content. 100×100 px
    // is the threshold modern editors converge on.
    if (img.naturalWidth < 100 || img.naturalHeight < 100) return
    setLightbox({ src: img.src, alt: img.alt })
  }

  return (
    <>
      <div
        ref={ref}
        onClick={handleClick}
        // `max-w-none` used to sit here and did nothing: `.prose{max-width:68ch}`
        // is later in the built stylesheet at equal specificity, so the measure
        // always won. One of the two was a lie; the measure is the one we meant.
        className="prose"
        dangerouslySetInnerHTML={{ __html: html }}
      />
      {lightbox && (
        <ImageLightbox
          src={lightbox.src}
          alt={lightbox.alt}
          onClose={() => setLightbox(null)}
        />
      )}
    </>
  )
}

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
        <TextBlockRender html={sanitizedContent} />
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
      className="group flex w-full items-center gap-3 rounded-md border border-edge dark:border-transparent bg-card px-4 py-3 text-left transition-colors hover:border-brand/40 hover:bg-muted/40 disabled:opacity-60"
      aria-label={t("chapter.downloadFileAria", { name: label })}
    >
      <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-muted">
        {opening ? (
          <Loader2 className="h-4 w-4 animate-spin text-ink-muted" strokeWidth={1.75} aria-hidden />
        ) : (
          <File className="h-4 w-4 text-ink-muted" strokeWidth={1.75} aria-hidden />
        )}
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-xs font-medium uppercase tracking-[0.18em] text-ink-muted">
          {t("chapter.attachmentEyebrow")}
        </p>
        <p className="mt-0.5 truncate text-sm font-medium text-ink">{label}</p>
      </div>
      <Download className="h-4 w-4 shrink-0 text-ink-muted transition-colors group-hover:text-brand" strokeWidth={1.75} aria-hidden />
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
      <div className="rounded-md border border-dashed border-edge bg-muted/20 px-5 py-12 text-center">
        <p className="text-sm text-ink-muted">
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
    "flex min-w-0 flex-1 cursor-not-allowed flex-col rounded-md bg-muted/20 px-3 py-2 opacity-60"
  const enabledClass =
    "group flex min-w-0 flex-1 flex-col rounded-md bg-card px-3 py-2 transition-colors hover:border-brand/40 hover:bg-muted/40"

  if (!chapter) {
    return (
      <div className={`${disabledClass} ${alignment}`} aria-hidden="true">
        <span className={`flex items-center gap-1.5 text-xs font-medium uppercase tracking-[0.18em] text-ink-muted ${justify}`}>
          {side === "prev" && <ArrowLeft className="h-3.5 w-3.5" strokeWidth={1.75} />}
          {eyebrow}
          {side === "next" && <ArrowRight className="h-3.5 w-3.5" strokeWidth={1.75} />}
        </span>
        <span className="mt-0.5 truncate text-sm text-ink-muted/70">
          {fallbackLabel}
        </span>
      </div>
    )
  }

  if (locked) {
    return (
      <div className={`${disabledClass} ${alignment}`} aria-label={fallbackLabel}>
        <span className={`flex items-center gap-1.5 text-xs font-medium uppercase tracking-[0.18em] text-ink-muted ${justify}`}>
          <Lock className="h-3.5 w-3.5" strokeWidth={1.75} />
          {eyebrow}
        </span>
        <span className="mt-0.5 truncate text-sm font-medium text-ink-muted">
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
        <span className={`flex items-center gap-1.5 text-xs font-medium uppercase tracking-[0.18em] text-ink-muted transition-colors group-hover:text-brand ${justify}`}>
          {side === "prev" && <ArrowLeft className="h-3.5 w-3.5" strokeWidth={1.75} />}
          {eyebrow}
          {side === "next" && <ArrowRight className="h-3.5 w-3.5" strokeWidth={1.75} />}
        </span>
        <span className="mt-0.5 truncate text-sm font-medium text-ink">
          {chapter.title}
        </span>
      </button>
    </PressFeedback>
  )
}

type EndOfModuleNav =
  | { kind: "nextModule"; moduleId: string; chapterId: string; title: string }
  | { kind: "finishCourse" }

/** "Next" tile for the last chapter of a module: next module's first
 *  chapter, or — after the last module — the course page (where the
 *  completion dialog / certificate request lives). */
function EndOfModuleNavLink({
  nav,
  courseId,
}: {
  nav: EndOfModuleNav
  courseId?: string
}) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const isFinish = nav.kind === "finishCourse"
  const eyebrow = isFinish ? t("chapter.finishEyebrow") : t("chapter.nextModuleEyebrow")
  const label = isFinish ? t("chapter.finishCourseLabel") : nav.title
  const target = isFinish
    ? `/courses/${courseId}`
    : `/courses/${courseId}/modules/${nav.moduleId}/chapters/${nav.chapterId}`

  return (
    <PressFeedback className="flex min-w-0 flex-1">
      <button
        type="button"
        onClick={() => navigate(target)}
        className="group flex min-w-0 flex-1 flex-col rounded-md bg-card px-3 py-2 text-right transition-colors hover:border-brand/40 hover:bg-muted/40"
        aria-label={`${eyebrow}: ${label}`}
      >
        <span className="flex items-center justify-end gap-1.5 text-xs font-medium uppercase tracking-[0.18em] text-ink-muted transition-colors group-hover:text-brand">
          {eyebrow}
          {isFinish ? (
            <CheckCircle className="h-3.5 w-3.5" strokeWidth={1.75} />
          ) : (
            <ArrowRight className="h-3.5 w-3.5" strokeWidth={1.75} />
          )}
        </span>
        <span className="mt-0.5 truncate text-sm font-medium text-ink">{label}</span>
      </button>
    </PressFeedback>
  )
}

function ChapterNav({
  prevChapter,
  nextChapter,
  endOfModuleNav,
  currentIdx,
  total,
  courseId,
  moduleId,
  isNextLocked,
}: {
  prevChapter: Chapter | null
  nextChapter: Chapter | null
  endOfModuleNav: EndOfModuleNav | null
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
      className="mt-10 border-t border-edge pt-6"
    >
      <p className="mb-3 text-center text-xs font-medium uppercase tracking-[0.18em] text-ink-muted tabular-nums">
        {t("chapter.positionEyebrow", { current: currentIdx + 1, total })}
      </p>
      <div className="flex items-stretch gap-2 sm:gap-3">
        <ChapterNavLink
          side="prev"
          chapter={prevChapter}
          courseId={courseId}
          moduleId={moduleId}
        />
        {!nextChapter && endOfModuleNav ? (
          <EndOfModuleNavLink nav={endOfModuleNav} courseId={courseId} />
        ) : (
          <ChapterNavLink
            side="next"
            chapter={nextChapter}
            courseId={courseId}
            moduleId={moduleId}
            locked={isNextLocked}
          />
        )}
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
  const [course, setCourse] = useState<Course | null>(null)
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
        const [m, completedChapterIds, fullCourse] = await Promise.all([
          coursesService.getModule(courseId, moduleId),
          coursesService.getMyChapterProgress(courseId).catch(() => [] as string[]),
          // Only needed to answer "is there a NEXT module after this one?"
          // for the end-of-module nav tile. Cached 3min and usually warm
          // (the student navigated here from the course page). On failure
          // the tile degrades to the old disabled placeholder.
          coursesService.getCourse(courseId).catch(() => null),
        ])
        if (cancelled) return
        setMod(m)
        setCourse(fullCourse)
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

  // Studying a chapter counts as opening the course for the dashboard's
  // "recently viewed" row. Signed-in only; filtered against real
  // enrollments at render time.
  useEffect(() => {
    if (user && courseId) {
      recordCourseView(courseId)
    }
  }, [user, courseId])

  const sortedChapters = useMemo(
    () => [...(mod?.chapters ?? [])].sort((a, b) => a.order_index - b.order_index),
    [mod],
  )

  const currentIdx = sortedChapters.findIndex((c) => c.id === chapterId)
  const chapter = currentIdx >= 0 ? sortedChapters[currentIdx] : null
  const prevChapter = currentIdx > 0 ? sortedChapters[currentIdx - 1] ?? null : null
  const nextChapter = currentIdx < sortedChapters.length - 1 ? sortedChapters[currentIdx + 1] ?? null : null

  // End-of-module navigation: when this is the last chapter of the module,
  // the "next" tile used to be a disabled placeholder — a literal dead end
  // at the most motivated moment of the course. Resolve where to go next:
  // the first chapter of the next module, or (after the last module) the
  // course page, where the completion dialog / certificate request lives.
  const endOfModuleNav = useMemo((): EndOfModuleNav | null => {
    if (nextChapter || !course?.modules?.length || !moduleId) return null
    const sortedModules = [...course.modules].sort((a, b) => a.order_index - b.order_index)
    const idx = sortedModules.findIndex((m) => m.id === moduleId)
    if (idx === -1) return null
    const nextWithChapters = sortedModules
      .slice(idx + 1)
      .find((m) => (m.chapters?.length ?? 0) > 0)
    if (nextWithChapters) {
      const first = [...(nextWithChapters.chapters ?? [])].sort(
        (a, b) => a.order_index - b.order_index,
      )[0]
      if (first) {
        return { kind: "nextModule", moduleId: nextWithChapters.id, chapterId: first.id, title: nextWithChapters.title }
      }
    }
    return { kind: "finishCourse" }
  }, [nextChapter, course, moduleId])

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

  const [markingRead, setMarkingRead] = useState(false)

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
          <Lock className="h-12 w-12 text-ink-muted mx-auto mb-4" strokeWidth={1.75} />
          <h2 className="font-serif text-xl font-semibold mb-2">{t("chapter.lockedTitle")}</h2>
          <p className="text-ink-muted">{t("chapter.lockedHint")}</p>
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
        <p className="mb-3 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs font-medium uppercase tracking-[0.18em] text-ink-muted">
          <span className="inline-flex items-center gap-1.5">
            <ChapterTypeIcon className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
            {t(CHAPTER_TYPE_LABEL_KEYS[chapterType])}
          </span>
          <span aria-hidden className="text-ink-muted/40">·</span>
          <span className="tabular-nums">
            {t("chapter.positionEyebrow", { current: currentIdx + 1, total: sortedChapters.length })}
          </span>
          {mod.title && (
            <>
              <span aria-hidden className="text-ink-muted/40">·</span>
              <span className="normal-case tracking-normal text-ink-muted/80 text-wrap-safe">
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

      {/* Reading chapters get an act of their own.
          Until now a chapter of pure text could not be finished by the person
          reading it — only a teacher could tick it — so the core act of the
          product left no trace. The control is explicit rather than a scroll
          heuristic: a heuristic credits the skimmer who reaches the bottom and
          misses the careful reader on a phone who closes the tab. */}
      {chapterType === "reading" && !hasAssignments && (
        <div className="mt-8 border-t border-edge pt-5">
          {isCompleted ? (
            <p className="flex items-center gap-2 text-sm font-medium text-success">
              <CheckCircle className="h-4 w-4 shrink-0" strokeWidth={1.75} aria-hidden />
              {t("chapter.markedRead")}
            </p>
          ) : (
            <Button
              variant="outline"
              size="sm"
              disabled={markingRead}
              onClick={async () => {
                setMarkingRead(true)
                try {
                  await progressService.markRead(chapter.id)
                  await refreshCompletion()
                } catch {
                  toast({ title: t("chapter.markReadFailed"), variant: "destructive" })
                } finally {
                  setMarkingRead(false)
                }
              }}
            >
              <CheckCircle className="mr-1.5 h-4 w-4" strokeWidth={1.75} aria-hidden />
              {t("chapter.markRead")}
            </Button>
          )}
        </div>
      )}

      {hasAssignments && (
        <div className="mt-6 border-t border-edge pt-5">
          {isCompleted ? (
            <p className="flex items-center gap-2 text-sm font-medium text-success">
              <CheckCircle className="h-4 w-4 shrink-0" strokeWidth={1.75} />
              {t("chapter.completed")}
            </p>
          ) : (
            <p className="flex items-center gap-2 text-sm text-ink-muted">
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
          endOfModuleNav={endOfModuleNav}
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
