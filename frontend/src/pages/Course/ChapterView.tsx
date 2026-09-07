import { useEffect, useRef, useState, useCallback, useMemo, memo } from "react"
import { useTranslation } from "react-i18next"
import { useParams, Link, useNavigate } from "react-router-dom"
import { isAxiosError } from "axios"
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
import {
  chapterHref,
  findChapter,
  readCourseStructure,
} from "@/lib/courseStructure"
import { isChapterLocked } from "./moduleProgress"
import type { Course, Chapter, ChapterBlock } from "@/types"
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
import { ReadingSkeleton } from "@/components/chapter/ReadingSkeleton"
import { orNotTranslated } from "@/lib/untranslated"

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
export function ChapterBodyBlocks({
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
  if (loading) return <ReadingSkeleton />
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
  // Blocks exist but none of them has anything to read in this
  // language. An empty text block renders as nothing, so without this
  // the lesson was a blank page under a heading — indistinguishable
  // from a bug in the reader's browser. "Nothing here" and "nothing
  // here *yet, in your language*" are different sentences.
  const hasSomethingToRead = blocks.some(
    (block) => block.block_type !== "text" || (block.content ?? "").trim().length > 0,
  )
  if (!hasSomethingToRead) {
    return (
      <div className="rounded-md border border-dashed border-edge bg-muted/20 px-5 py-12 text-center">
        <p className="text-sm text-ink-muted">{t("chapter.notTranslated")}</p>
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
  locked,
}: {
  side: "prev" | "next"
  chapter: Chapter | null
  courseId: string
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
        <span className="mt-0.5 truncate text-sm text-ink-muted">
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
          {orNotTranslated(t, chapter.title)}
        </span>
      </div>
    )
  }

  return (
    <PressFeedback className="flex min-w-0 flex-1">
      <button
        type="button"
        onClick={() => navigate(chapterHref(courseId, chapter.id))}
        className={`${enabledClass} ${alignment}`}
        aria-label={`${eyebrow}: ${orNotTranslated(t, chapter.title)}`}
      >
        <span className={`flex items-center gap-1.5 text-xs font-medium uppercase tracking-[0.18em] text-ink-muted transition-colors group-hover:text-brand ${justify}`}>
          {side === "prev" && <ArrowLeft className="h-3.5 w-3.5" strokeWidth={1.75} />}
          {eyebrow}
          {side === "next" && <ArrowRight className="h-3.5 w-3.5" strokeWidth={1.75} />}
        </span>
        <span className="mt-0.5 truncate text-sm font-medium text-ink">
          {orNotTranslated(t, chapter.title)}
        </span>
      </button>
    </PressFeedback>
  )
}

/**
 * The "next" tile for the last lesson of the course: the course page, where
 * the completion dialog and the certificate request live.
 *
 * There used to be a second kind of tile here — "next module" — because
 * "next" walked the module and then had to be told, separately, how to leave
 * it. The flat reading order crosses that boundary on its own: the last lesson
 * of a module leads into the first of the next one like any other step, and
 * only the last lesson of the *course* has nowhere further to go. One dead end
 * remained, and it is the one that should be there.
 */
function FinishCourseNavLink({ courseId }: { courseId: string }) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const eyebrow = t("chapter.finishEyebrow")
  const label = t("chapter.finishCourseLabel")

  return (
    <PressFeedback className="flex min-w-0 flex-1">
      <button
        type="button"
        onClick={() => navigate(`/courses/${courseId}`)}
        className="group flex min-w-0 flex-1 flex-col rounded-md bg-card px-3 py-2 text-right transition-colors hover:border-brand/40 hover:bg-muted/40"
        aria-label={`${eyebrow}: ${label}`}
      >
        <span className="flex items-center justify-end gap-1.5 text-xs font-medium uppercase tracking-[0.18em] text-ink-muted transition-colors group-hover:text-brand">
          {eyebrow}
          <CheckCircle className="h-3.5 w-3.5" strokeWidth={1.75} />
        </span>
        <span className="mt-0.5 truncate text-sm font-medium text-ink">{label}</span>
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
  isNextLocked,
}: {
  prevChapter: Chapter | null
  nextChapter: Chapter | null
  currentIdx: number
  total: number
  courseId: string
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
        <ChapterNavLink side="prev" chapter={prevChapter} courseId={courseId} />
        {nextChapter ? (
          <ChapterNavLink
            side="next"
            chapter={nextChapter}
            courseId={courseId}
            locked={isNextLocked}
          />
        ) : (
          <FinishCourseNavLink courseId={courseId} />
        )}
      </div>
    </nav>
  )
}

/**
 * A lesson, and the course around it.
 *
 * The screen used to be built out of the *module*: it fetched
 * `getModule(courseId, moduleId)`, sorted that module's chapters, and walked
 * them for "previous" and "next". Three things followed from that, and all
 * three were wrong:
 *
 * - the walk stopped at the module's edge, so the last lesson of a module
 *   needed a second, separate rule to find the next module;
 * - a lesson in no module had no walk at all — no module to sort, no
 *   neighbours, no "next" under any rule;
 * - and `moduleId` was required before anything loaded, so the course-shaped
 *   address the router already accepts died on a guard with «invalid link».
 *
 * It is built out of the course now: one payload, read by `readCourseStructure`
 * into the reading order, and `findChapter` says where this lesson sits in it.
 * `moduleId` is not read at all — the module-shaped address still resolves,
 * and resolves to the same page, because the lesson's place was never a fact
 * about the URL.
 */
export default function ChapterView() {
  const { t, i18n } = useTranslation()
  const { courseId, chapterId } = useParams<{
    courseId: string
    chapterId: string
  }>()
  const { user } = useAuth()

  const [course, setCourse] = useState<Course | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  /**
   * `null` when the progress request failed. Not an empty set.
   *
   * `new Set(null)` is an empty Set rather than a throw, so the old fallback
   * turned "we could not find out" into "you have completed nothing" without
   * so much as an error — and `isChapterLocked` below then walled the student
   * out of a chapter they had earned. See `moduleProgress.ts`.
   */
  const [completedIds, setCompletedIds] = useState<Set<string> | null>(null)
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
    ready: !loading && !error && course !== null,
  })

  useEffect(() => {
    let cancelled = false
    const load = async () => {
      // `moduleId` used to be required here, which made the course-shaped
      // address — the one every lesson has — fail before a single request
      // went out. What the page needs is a course and a lesson.
      if (!courseId || !chapterId) {
        setLoading(false)
        setError(t("errors.invalidCourseLink"))
        return
      }
      setLoading(true)
      setError(null)
      try {
        // The course, not the module. It is the whole structure: the reading
        // order, the group this lesson belongs to (if any), and the lesson
        // itself. Cached 3min and usually warm — the student came here from
        // the course page. It is no longer optional, because losing it is
        // losing the lesson, not just the tile at the bottom.
        const [fullCourse, completedChapterIds] = await Promise.all([
          coursesService.getCourse(courseId),
          // See `moduleProgress.ts` — `[]` and "unknown" must not be the
          // same value. Here it only drives the read tick, which now simply
          // does not draw rather than drawing a false "not read".
          coursesService.getMyChapterProgress(courseId).catch(() => null),
        ])
        if (cancelled) return
        setCourse(fullCourse)
        setCompletedIds(completedChapterIds === null ? null : new Set(completedChapterIds))
      } catch (err) {
        if (!cancelled) {
          setError(
            isAxiosError(err) && err.response?.status === 404
              ? t("toast.chapterNotFound")
              : t("errors.loadChapterFailed"),
          )
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => { cancelled = true }
    // ``i18n.language`` so locale flip refreshes the localised course
    // structure. ``t`` is intentionally not a dep, and neither is
    // ``chapterId``: the course is the same course when the reader steps to
    // the next lesson, and re-running this would spend a progress request on
    // every step through it.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [courseId, user?.id, i18n.language])

  // Studying a chapter counts as opening the course for the dashboard's
  // "recently viewed" row. Signed-in only; filtered against real
  // enrollments at render time.
  useEffect(() => {
    if (user && courseId) {
      recordCourseView(courseId)
    }
  }, [user, courseId])

  // One reading of the course, and one answer to "where am I in it". The
  // walk this replaces was two levels deep and could only ever answer within
  // a module; `placement.prev` / `placement.next` step through the course.
  const structure = useMemo(() => readCourseStructure(course), [course])
  const placement = findChapter(structure, chapterId)

  const chapter = placement?.chapter ?? null
  const currentIdx = placement?.index ?? -1
  const prevChapter = placement?.prev ?? null
  const nextChapter = placement?.next ?? null
  // The module this lesson is grouped under, if anything is. `null` is an
  // ordinary answer now, not a broken payload — so nothing that depends on it
  // may be on the path a lesson without one has to walk.
  const parentModule = placement?.group.module ?? null
  const backHref = parentModule
    ? `/courses/${courseId}/modules/${parentModule.id}`
    : `/courses/${courseId}`
  const backLabel = parentModule ? t("course.backToModule") : t("course.backToCourse")

  /**
   * The chapter's own text, fetched from the URL rather than from the course.
   *
   * Measured on production before changing this: **10.7 seconds to first
   * text.** The timeline said exactly why — `/courses/{id}` took 5.6s, and
   * `/blocks/chapter/{id}` did not *start* until 9,842ms, because this effect
   * waited for `chapter` to exist. The one thing the student came for was the
   * last thing requested, behind a call it needs nothing from.
   *
   * `chapterId` is in the URL, so the fetch can start immediately and run
   * beside everything else. The type guard moves to a check on what we know:
   * if the course has arrived and says this is not a reading chapter, skip;
   * if it has not arrived yet, fetch. The cost is one wasted request when a
   * student opens a quiz or an assignment; the saving is five and a half
   * seconds of blank screen on every reading chapter, which is most of them
   * and is the surface this product exists to serve.
   */
  useEffect(() => {
    if (!chapterId) return
    let cancelled = false

    setHasAssignments(false)

    // Only reading chapters carry blocks; quiz/exam/assignment render their
    // own dedicated panels. `chapter` may not have arrived yet — in that case
    // we fetch rather than wait, which is the entire point.
    if (chapter && normalizeChapterType(chapter.chapter_type) !== "reading") {
      setChapterBlocks([])
      return
    }

    setLoadingBlocks(true)
    setBlocksLoadError(false)
    coursesService
      .getChapterBlocks(chapterId)
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
    // `chapterId` drives it, not `chapter` — that dependency was the
    // waterfall. `chapter` stays so the type guard re-runs once the course
    // lands and can discard blocks for a non-reading chapter.
  }, [chapterId, chapter, i18n.language, blocksReloadKey])

  /**
   * Is this lesson walled off until the one before it is done?
   *
   * "The one before it" is the course's order now, not the module's. It was a
   * private copy of `moduleProgress.isChapterLocked` that walked the module's
   * chapters — so the first lesson of every module was unlocked by accident of
   * being at index 0, and a lesson in no module was never gated at all. The
   * shared helper is the same rule the outline and the module page apply, and
   * it fails open on unknown progress for the reason written there.
   */
  const isLockedAt = useCallback(
    (idx: number) => {
      const ch = structure.chapters[idx]
      if (!ch) return false
      const prev = structure.chapters[idx - 1] ?? null
      return isChapterLocked(
        completedIds,
        ch,
        prev,
        prev ? isGradableChapterType(prev.chapter_type) : false,
      )
    },
    [structure, completedIds],
  )

  const [markingRead, setMarkingRead] = useState(false)

  const refreshCompletion = useCallback(async () => {
    if (!chapter || !courseId) return
    try {
      const completedChapterIds = await coursesService.getMyChapterProgress(courseId)
      setCompletedIds(completedChapterIds === null ? null : new Set(completedChapterIds))
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

  if (error || !courseId || !chapter) {
    return (
      <div className="container mx-auto px-4">
        <ErrorState
          icon={<Book strokeWidth={1.75} />}
          title={error ?? t("toast.chapterNotFound")}
          action={
            // Back to the course, not to a module. A lesson that could not be
            // found may have been in no module, and a lesson that was deleted
            // takes the answer to "which module" with it — the course is the
            // one place that is certainly still there.
            courseId ? (
              <Link to={`/courses/${courseId}`}>
                <Button variant="outline" size="sm">{t("course.backToCourse")}</Button>
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

  const locked = isLockedAt(currentIdx)
  const isCompleted = completedIds !== null && completedIds.has(chapter.id)

  if (locked) {
    return (
      <div className="container mx-auto px-4 py-6 max-w-3xl">
        <Link to={backHref} className="-mx-2 mb-4 inline-flex">
          <Button variant="ghost" size="sm" className="h-11 text-xs sm:h-8">
            <ArrowLeft className="mr-1.5 h-4 w-4" strokeWidth={1.75} aria-hidden />
            {backLabel}
          </Button>
        </Link>

        <div className="text-center py-16">
          <Lock className="h-12 w-12 text-ink-muted mx-auto mb-4" strokeWidth={1.75} />
          <h2 className="font-serif text-xl font-semibold mb-2">{t("chapter.lockedTitle")}</h2>
          <p className="text-ink-muted">{t("chapter.lockedHint")}</p>
          {prevChapter && (
            <Link to={chapterHref(courseId, prevChapter.id)}>
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
      {/* Back to whatever holds this lesson: its module when one groups it,
          the course when nothing does. «К модулю» over a lesson that is in no
          module was a door with nothing behind it. */}
      <Link to={backHref} className="-mx-2 mb-6 inline-flex">
        <Button variant="ghost" size="sm" className="h-11 text-xs sm:h-8">
          <ArrowLeft className="mr-1.5 h-4 w-4" strokeWidth={1.75} aria-hidden />
          {backLabel}
        </Button>
      </Link>

      <header data-tour="chapter-header" className="mb-10">
        <p className="mb-3 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs font-medium uppercase tracking-[0.18em] text-ink-muted">
          <span className="inline-flex items-center gap-1.5">
            <ChapterTypeIcon className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
            {t(CHAPTER_TYPE_LABEL_KEYS[chapterType])}
          </span>
          <span aria-hidden className="text-ink-muted">·</span>
          <span className="tabular-nums">
            {/* The lesson's place in the course, not in its module. «Глава 1
                из 3» on the first lesson of the second module told a student
                they were at the start of something they were halfway through. */}
            {t("chapter.positionEyebrow", { current: currentIdx + 1, total: structure.chapters.length })}
          </span>
          {parentModule?.title && (
            <>
              <span aria-hidden className="text-ink-muted">·</span>
              <span className="normal-case tracking-normal text-ink-muted text-wrap-safe">
                {parentModule.title}
              </span>
            </>
          )}
        </p>
        <h1 className="font-serif text-3xl font-semibold tracking-tight text-wrap-safe sm:text-4xl">
          {orNotTranslated(t, chapter.title)}
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
          currentIdx={currentIdx}
          total={structure.chapters.length}
          courseId={courseId}
          isNextLocked={isLockedAt(currentIdx + 1)}
        />
      </div>
    </div>
  )
}
