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
} from "lucide-react"
import QuizTaker from "@/components/quiz/QuizTaker"
import AssignmentPanel from "@/components/assignment/AssignmentPanel"
import {
  isGradableChapterType,
  normalizeChapterType,
} from "@/lib/chapterTypes"
import ChapterTypeBadge from "@/components/course/ChapterTypeBadge"
import { ErrorState } from "@/components/patterns"

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
      className="inline-flex items-center gap-2 rounded-md border px-3 py-2 text-sm transition-colors hover:bg-muted/50 disabled:opacity-60"
    >
      {opening ? (
        <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" strokeWidth={1.75} aria-hidden />
      ) : (
        <File className="h-4 w-4 text-muted-foreground" strokeWidth={1.75} aria-hidden />
      )}
      <span>{label}</span>
      <Download className="h-4 w-4 text-muted-foreground" strokeWidth={1.75} aria-hidden />
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
  onProgressChanged,
  onAssignmentCountLoaded,
}: {
  loading: boolean
  blocks: ChapterBlock[]
  onProgressChanged?: () => void
  onAssignmentCountLoaded?: (count: number) => void
}) {
  const { t } = useTranslation()
  if (loading) return <PageSpinner variant="section" />
  if (blocks.length === 0) {
    return (
      <p className="text-muted-foreground text-center py-8">
        {t("chapter.emptyContent")}
      </p>
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
  const navigate = useNavigate()

  return (
    <div className="mt-8 pt-6 border-t flex items-center justify-between">
      {prevChapter ? (
        <Button
          variant="outline"
          onClick={() => navigate(`/courses/${courseId}/modules/${moduleId}/chapters/${prevChapter.id}`)}
          className="gap-2"
        >
          <ArrowLeft className="h-4 w-4" strokeWidth={1.75} aria-hidden />
          {t("chapter.prevChapter")}
        </Button>
      ) : (
        <Button variant="outline" disabled className="gap-2">
          <ArrowLeft className="h-4 w-4" strokeWidth={1.75} aria-hidden />
          {t("chapter.prevChapter")}
        </Button>
      )}

      <span className="text-xs text-muted-foreground">
        {currentIdx + 1}/{total}
      </span>

      {nextChapter ? (
        isNextLocked ? (
          <Button variant="outline" disabled className="gap-2">
            <Lock className="h-4 w-4" strokeWidth={1.75} aria-hidden />
            {t("chapter.nextChapter")}
          </Button>
        ) : (
          <Button
            variant="outline"
            onClick={() => navigate(`/courses/${courseId}/modules/${moduleId}/chapters/${nextChapter.id}`)}
            className="gap-2"
          >
            {t("chapter.nextChapter")}
            <ArrowRight className="h-4 w-4" strokeWidth={1.75} aria-hidden />
          </Button>
        )
      ) : (
        <Button variant="outline" disabled className="gap-2">
          {t("chapter.nextChapter")}
          <ArrowRight className="h-4 w-4" strokeWidth={1.75} aria-hidden />
        </Button>
      )}
    </div>
  )
}

export default function ChapterView() {
  const { t } = useTranslation()
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
  const [hasAssignments, setHasAssignments] = useState(false)

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
  }, [courseId, moduleId, user?.id, t])

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
    coursesService
      .getChapterBlocks(chapter.id)
      .catch(() => [] as ChapterBlock[])
      .then((blocks) => {
        if (cancelled) return
        setChapterBlocks(blocks.sort((a, b) => a.order_index - b.order_index))
        setLoadingBlocks(false)
      })

    return () => { cancelled = true }
  }, [chapter])

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
          icon={<Book />}
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
        <Link to={`/courses/${courseId}/modules/${moduleId}`}>
          <Button variant="ghost" size="sm" className="mb-4 h-8 text-xs">
            <ArrowLeft className="mr-1.5 h-4 w-4" strokeWidth={1.75} aria-hidden />
            {t("course.backToModule")}
          </Button>
        </Link>

        <div className="text-center py-16">
          <Lock className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
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

  return (
    <div className="container mx-auto px-4 py-6 max-w-3xl">
      <Link to={`/courses/${courseId}/modules/${moduleId}`}>
        <Button variant="ghost" size="sm" className="mb-6 h-8 text-xs">
          <ArrowLeft className="mr-1.5 h-4 w-4" strokeWidth={1.75} aria-hidden />
          {t("course.backToModule")}
        </Button>
      </Link>

      <div className="mb-8">
        <div className="mb-3">
          <ChapterTypeBadge type={chapterType} />
        </div>
        <h1 className="mb-1 font-serif text-3xl font-bold tracking-tight text-wrap-safe">
          {chapter.title}
        </h1>
        <p className="text-sm text-muted-foreground text-wrap-safe">
          {t("chapter.chapterOf", { current: currentIdx + 1, total: sortedChapters.length })}
          {mod.title && <> &middot; {mod.title}</>}
        </p>
      </div>

      <div className="mb-8 space-y-6">
        {chapterType === "reading" && (
          <ChapterBodyBlocks
            loading={loadingBlocks}
            blocks={chapterBlocks}
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
        <div className="mt-6 pt-4 border-t">
          {isCompleted ? (
            <p className="flex items-center gap-2 text-sm text-success">
              <CheckCircle className="h-4 w-4" />
              {t("chapter.completed")}
            </p>
          ) : (
            <p className="text-sm text-muted-foreground flex items-center gap-2">
              <Circle className="h-4 w-4" />
              {t("chapter.submitAssignmentToComplete")}
            </p>
          )}
        </div>
      )}

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
  )
}
