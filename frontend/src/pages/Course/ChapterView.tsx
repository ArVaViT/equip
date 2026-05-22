import { useEffect, useState, useCallback, useMemo, memo } from "react"
import { useParams, Link, useNavigate } from "react-router-dom"
import { sanitizeHtml as sanitize } from "@/lib/sanitize"
import PageSpinner from "@/components/ui/PageSpinner"
import { Button } from "@/components/ui/button"
import { coursesService } from "@/services/courses"
import { storageService } from "@/services/storage"
import { toast } from "@/lib/toast"
import { useAuth } from "@/context/useAuth"
import type { Module, Chapter, ChapterBlock } from "@/types"
import { usePageTitle } from "@/hooks/usePageTitle"
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
          label={block.file_name || block.content || "Download file"}
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
      toast({ title: "Could not open file. Please try again.", variant: "destructive" })
    } finally {
      setOpening(false)
    }
  }, [bucket, path, opening])



  return (
    <button
      type="button"
      onClick={handleClick}
      disabled={opening}
      className="inline-flex items-center gap-2 rounded-lg border px-3 py-2 text-sm hover:bg-muted/50 transition-colors disabled:opacity-60"
    >
      {opening ? (
        <Loader2 className="h-4 w-4 text-muted-foreground animate-spin" />
      ) : (
        <File className="h-4 w-4 text-muted-foreground" />
      )}
      <span>{label}</span>
      <Download className="h-3.5 w-3.5 text-muted-foreground" />
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
  if (loading) return <PageSpinner variant="section" />
  if (blocks.length === 0) {
    return (
      <p className="text-muted-foreground text-center py-8">
        No content has been added to this chapter yet.
      </p>
    )
  }
  return (
    <div className="space-y-6">
      {blocks.map((block) => (
        <BlockRenderer
          key={block.id}
          block={block}
          onProgressChanged={onProgressChanged}
          onAssignmentCountLoaded={onAssignmentCountLoaded}
        />
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
  const navigate = useNavigate()

  return (
    <div className="mt-8 pt-6 border-t flex items-center justify-between">
      {prevChapter ? (
        <Button
          variant="outline"
          onClick={() => navigate(`/courses/${courseId}/modules/${moduleId}/chapters/${prevChapter.id}`)}
          className="gap-2"
        >
          <ArrowLeft className="h-4 w-4" />
          Previous Chapter
        </Button>
      ) : (
        <Button variant="outline" disabled className="gap-2">
          <ArrowLeft className="h-4 w-4" />
          Previous Chapter
        </Button>
      )}

      <span className="text-xs text-muted-foreground">
        {currentIdx + 1}/{total}
      </span>

      {nextChapter ? (
        isNextLocked ? (
          <Button variant="outline" disabled className="gap-2">
            <Lock className="h-4 w-4" />
            Next Chapter
          </Button>
        ) : (
          <Button
            variant="outline"
            onClick={() => navigate(`/courses/${courseId}/modules/${moduleId}/chapters/${nextChapter.id}`)}
            className="gap-2"
          >
            Next Chapter
            <ArrowRight className="h-4 w-4" />
          </Button>
        )
      ) : (
        <Button variant="outline" disabled className="gap-2">
          Next Chapter
          <ArrowRight className="h-4 w-4" />
        </Button>
      )}
    </div>
  )
}

export default function ChapterView() {
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
        setError("Invalid course or module link.")
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
        if (!cancelled) setError("Failed to load chapter. Please try again.")
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => { cancelled = true }
  }, [courseId, moduleId, user?.id])

  const sortedChapters = useMemo(
    () => [...(mod?.chapters ?? [])].sort((a, b) => a.order_index - b.order_index),
    [mod],
  )

  const currentIdx = sortedChapters.findIndex((c) => c.id === chapterId)
  const chapter = currentIdx >= 0 ? sortedChapters[currentIdx] : null
  const prevChapter = currentIdx > 0 ? sortedChapters[currentIdx - 1] ?? null : null
  const nextChapter = currentIdx < sortedChapters.length - 1 ? sortedChapters[currentIdx + 1] ?? null : null

  usePageTitle(
    chapter?.title && mod?.title
      ? `${mod.title} - ${chapter.title}`
      : chapter?.title
  )

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
          title={error ?? "Chapter not found"}
          action={
            courseId && moduleId ? (
              <Link to={`/courses/${courseId}/modules/${moduleId}`}>
                <Button variant="outline" size="sm">Back to Module</Button>
              </Link>
            ) : (
              <Link to="/">
                <Button variant="outline" size="sm">Go Home</Button>
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
            <ArrowLeft className="h-3.5 w-3.5 mr-1.5" />
            Back to Module
          </Button>
        </Link>

        <div className="text-center py-16">
          <Lock className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
          <h2 className="font-serif text-xl font-semibold mb-2">Chapter Locked</h2>
          <p className="text-muted-foreground">Complete the previous chapter to unlock this one.</p>
          {prevChapter && (
            <Link to={`/courses/${courseId}/modules/${moduleId}/chapters/${prevChapter.id}`}>
              <Button className="mt-4">Go to Previous Chapter</Button>
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
          <ArrowLeft className="h-3.5 w-3.5 mr-1.5" />
          Back to Module
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
          Chapter {currentIdx + 1} of {sortedChapters.length}
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
              Completed
            </p>
          ) : (
            <p className="text-sm text-muted-foreground flex items-center gap-2">
              <Circle className="h-4 w-4" />
              Submit the assignment to complete this chapter
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
