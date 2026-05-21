import { useEffect, useState, useCallback } from "react"
import { useParams, Link, useNavigate } from "react-router-dom"
import { useTranslation } from "react-i18next"
import { getErrorDetail } from "@/lib/errorDetail"
import { Card, CardContent } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import ChapterBlockEditor from "@/components/editor/ChapterBlockEditor"
import QuizEditor from "@/components/quiz/QuizEditor"
import AssignmentEditor from "@/components/assignment/AssignmentEditor"
import { coursesService } from "@/services/courses"
import type { Chapter } from "@/types"
import { toast } from "@/lib/toast"
import { makeChapterSchema } from "@/lib/validations/course"
import { useConfirm } from "@/components/ui/alert-dialog"
import {
  ChevronRight, Save, Loader2, ArrowLeft,
} from "lucide-react"
import {
  CHAPTER_TYPES,
  CHAPTER_TYPE_META,
  normalizeChapterType,
  type ChapterType,
} from "@/lib/chapterTypes"
import { ErrorState } from "@/components/patterns"
import { Skeleton } from "@/components/ui/skeleton"
import { useUserTour } from "@/hooks/useUserTour"
import { chapterEditorSteps } from "@/lib/tourSteps"

const EDITOR_OPTIONS = CHAPTER_TYPES.map((value) => ({
  value,
  icon: CHAPTER_TYPE_META[value].icon,
}))

type ChapterUpdatePayload = Parameters<typeof coursesService.updateChapter>[3]

export default function ChapterEditor() {
  const { courseId, moduleId, chapterId } = useParams<{
    courseId: string
    moduleId: string
    chapterId: string
  }>()
  const navigate = useNavigate()
  const confirm = useConfirm()
  const { t } = useTranslation()

  const [chapter, setChapter] = useState<Chapter | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  const [title, setTitle] = useState("")
  const [chapterType, setChapterType] = useState<ChapterType>("reading")
  const [moduleName, setModuleName] = useState(() => t("chapterEditor.moduleFallback"))
  const [isDirty, setIsDirty] = useState(false)

  useUserTour({
    tourId: "chapter-editor-v1",
    steps: chapterEditorSteps(t),
    ready: !loading && chapter !== null,
  })

  const load = useCallback(async (signal?: { cancelled: boolean }) => {
    if (!courseId || !moduleId || !chapterId) return
    setLoading(true)
    try {
      // Editor-only fetch so the breadcrumb's ``moduleName`` + the chapter
      // title render in the source language regardless of the viewer's UI
      // locale. Keeps the editor unambiguous: what you see is what you'd
      // PATCH back.
      const mod = await coursesService.getModuleForEdit(courseId, moduleId)
      if (signal?.cancelled) return
      setModuleName(mod.title)
      const ch = mod.chapters?.find((c) => c.id === chapterId)
      if (!ch) {
        toast({ title: t("chapterEditor.toast.chapterNotFound"), variant: "destructive" })
        navigate(`/teacher/courses/${courseId}/modules/${moduleId}/edit`)
        return
      }
      setChapter(ch)
      setTitle(ch.title)
      const resolvedType = normalizeChapterType(ch.chapter_type)
      setChapterType(resolvedType)
      setInitialSnapshot(JSON.stringify({
        title: ch.title,
        chapterType: resolvedType,
      }))
      setIsDirty(false)
    } catch {
      if (signal?.cancelled) return
      toast({ title: t("chapterEditor.toast.loadFailed"), variant: "destructive" })
      navigate(`/teacher/courses/${courseId}/modules/${moduleId}/edit`)
    } finally {
      if (!signal?.cancelled) setLoading(false)
    }
  }, [courseId, moduleId, chapterId, navigate, t])

  useEffect(() => {
    const signal = { cancelled: false }
    load(signal)
    return () => { signal.cancelled = true }
  }, [load])

  const [initialSnapshot, setInitialSnapshot] = useState("")

  useEffect(() => {
    if (!chapter) return
    const snapshot = JSON.stringify({ title, chapterType })
    if (!initialSnapshot) {
      setInitialSnapshot(snapshot)
      return
    }
    setIsDirty(snapshot !== initialSnapshot)
  }, [chapter, title, chapterType, initialSnapshot])

  useEffect(() => {
    if (!isDirty) return
    const handleBeforeUnload = (e: BeforeUnloadEvent) => {
      e.preventDefault()
    }
    window.addEventListener("beforeunload", handleBeforeUnload)
    return () => window.removeEventListener("beforeunload", handleBeforeUnload)
  }, [isDirty])

  const save = useCallback(async () => {
    if (!courseId || !moduleId || !chapterId || !title.trim()) return
    // Only title + chapter_type live on the chapter row now. Reading content
    // is owned by chapter_blocks (edited inline inside ChapterBlockEditor,
    // which auto-saves). Quiz/exam/assignment editors write their own rows.
    // Build the schema inside the handler so error messages match
    // the *current* locale, not the bootstrap snapshot.
    const validation = makeChapterSchema().safeParse({
      title: title.trim(),
      chapter_type: chapterType,
    })
    if (!validation.success) {
      const first = validation.error.issues[0]
      toast({
        title: first?.message ?? t("chapterEditor.toast.invalidData"),
        variant: "destructive",
      })
      return
    }
    setSaving(true)
    try {
      const payload: ChapterUpdatePayload = {
        title: title.trim(),
        chapter_type: chapterType,
      }

      await coursesService.updateChapter(courseId, moduleId, chapterId, payload)
      const snapshot = JSON.stringify({ title: title.trim(), chapterType })
      setInitialSnapshot(snapshot)
      setIsDirty(false)
      toast({ title: t("chapterEditor.toast.saved") })
    } catch (error: unknown) {
      const detail = getErrorDetail(error) || t("chapterEditor.unknownError")
      toast({
        title: t("chapterEditor.toast.saveFailed", { detail }),
        variant: "destructive",
      })
    } finally {
      setSaving(false)
    }
  }, [courseId, moduleId, chapterId, title, chapterType, t])

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "s") {
        e.preventDefault()
        save()
      }
    }
    document.addEventListener("keydown", handleKeyDown)
    return () => document.removeEventListener("keydown", handleKeyDown)
  }, [save])

  // Shared dirty-check used by the Back button and every breadcrumb
  // link. Pre-fix, only the Back button asked before discarding work;
  // a click on any breadcrumb crumb silently navigated away. Three of
  // them — easy to miss when you've just typed two paragraphs.
  const guardedNavigate = useCallback(
    async (to: string) => {
      if (isDirty) {
        const ok = await confirm({
          title: t("chapterEditor.leaveConfirm.title"),
          description: t("chapterEditor.leaveConfirm.description"),
          confirmLabel: t("chapterEditor.leaveConfirm.confirm"),
          tone: "destructive",
        })
        if (!ok) return
      }
      navigate(to)
    },
    [confirm, isDirty, navigate, t],
  )

  // Click interceptor for breadcrumb ``<Link>`` elements. Only swallows
  // the plain left-click; Ctrl/Cmd/Shift/middle-click pass through to
  // the browser default so open-in-new-tab still works without a
  // confirm prompt (a new tab doesn't lose the editor's draft).
  const handleNavClick = (
    e: React.MouseEvent<HTMLAnchorElement>,
    to: string,
  ) => {
    if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return
    e.preventDefault()
    void guardedNavigate(to)
  }

  if (loading) {
    return (
      <div className="container mx-auto px-4 py-8 max-w-4xl">
        <Skeleton className="h-5 w-48 mb-6" />
        <Skeleton className="h-10 w-3/4 mb-4" />
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
          {[1, 2, 3, 4].map((i) => (
            <Skeleton key={i} className="h-24 rounded-lg" />
          ))}
        </div>
        <Skeleton className="h-64" />
      </div>
    )
  }

  if (!chapter) return (
    <div className="container mx-auto px-4">
      <ErrorState
        title={t("chapterEditor.notFound.title")}
        description={t("chapterEditor.notFound.description")}
        action={
          <Button
            variant="outline"
            size="sm"
            onClick={() => navigate(`/teacher/courses/${courseId}/modules/${moduleId}/edit`)}
          >
            {t("chapterEditor.notFound.backToModule")}
          </Button>
        }
      />
    </div>
  )

  return (
    <div className="container mx-auto max-w-4xl px-4 py-6 sm:py-8">
      {/* Breadcrumb — earlier crumbs hide on mobile to keep one line.
          Each link intercepts normal-button clicks so the dirty-check
          confirm fires before navigation; Ctrl/Cmd/Shift/middle-click
          fall through to the browser default (open-in-new-tab etc.)
          unchanged. */}
      <div className="mb-6 flex items-center gap-2 text-sm text-muted-foreground">
        <Link
          to="/teacher"
          onClick={(e) => handleNavClick(e, "/teacher")}
          className="hidden transition-colors hover:text-foreground sm:inline"
        >
          {t("chapterEditor.breadcrumb.myCourses")}
        </Link>
        <ChevronRight className="hidden h-3.5 w-3.5 sm:inline-block" strokeWidth={1.75} />
        <Link
          to={`/teacher/courses/${courseId}`}
          onClick={(e) => handleNavClick(e, `/teacher/courses/${courseId}`)}
          className="hidden transition-colors hover:text-foreground sm:inline"
        >
          {t("chapterEditor.breadcrumb.course")}
        </Link>
        <ChevronRight className="hidden h-3.5 w-3.5 sm:inline-block" strokeWidth={1.75} />
        <Link
          to={`/teacher/courses/${courseId}/modules/${moduleId}/edit`}
          onClick={(e) =>
            handleNavClick(e, `/teacher/courses/${courseId}/modules/${moduleId}/edit`)
          }
          className="min-w-0 truncate transition-colors hover:text-foreground"
        >
          {moduleName}
        </Link>
        <ChevronRight className="h-3.5 w-3.5 shrink-0" strokeWidth={1.75} />
        <span className="min-w-0 truncate font-medium text-foreground sm:max-w-[200px]">
          {title || t("chapterEditor.chapterFallback")}
        </span>
      </div>

      {/* Back button + title row */}
      <div data-tour="chapter-editor-header" className="flex items-center gap-3 mb-6">
        <Button
          variant="ghost"
          size="sm"
          className="shrink-0"
          onClick={() =>
            void guardedNavigate(
              `/teacher/courses/${courseId}/modules/${moduleId}/edit`,
            )
          }
        >
          <ArrowLeft className="h-4 w-4 mr-1" strokeWidth={1.75} />
          {t("chapterEditor.back")}
        </Button>
        {/* Render the editable title as a real ``<h1>`` so the page
            outline has the chapter name at heading-level-1, and add
            ``aria-label`` so the input still has an accessible name
            even though its visual label is implicit. */}
        <h1 className="m-0 flex-1">
          <Input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            aria-label={t("chapterEditor.editTitleAria")}
            className="font-serif text-2xl font-bold border-none shadow-none hover:border-border/50 hover:shadow-sm focus-visible:ring-1 h-auto py-1 px-2 w-full"
            placeholder={t("chapterEditor.titlePlaceholder")}
          />
        </h1>
      </div>

      {/* Chapter Type Selector */}
      <div className="mb-6">
        <Label className="text-sm font-semibold mb-3 block">
          {t("chapterEditor.chapterType")}
        </Label>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {EDITOR_OPTIONS.map((ct) => {
            const Icon = ct.icon
            const selected = chapterType === ct.value
            return (
              <button
                key={ct.value}
                type="button"
                onClick={() => setChapterType(ct.value)}
                aria-pressed={selected}
                className={`flex items-start gap-3 rounded-md border p-4 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 ${
                  selected
                    ? "border-primary bg-primary/[0.08] ring-1 ring-primary/40 dark:bg-primary/15"
                    : "border-border hover:border-primary/30 hover:bg-muted/40"
                }`}
              >
                <Icon
                  className={`h-5 w-5 mt-0.5 shrink-0 ${
                    selected ? "text-primary" : "text-muted-foreground"
                  }`}
                  strokeWidth={1.75}
                  aria-hidden
                />
                <div>
                  <div
                    className={`text-sm font-medium ${
                      selected ? "text-primary" : ""
                    }`}
                  >
                    {t(`chapterTypes.${ct.value}.label`)}
                  </div>
                  <div className="text-xs text-muted-foreground mt-0.5">
                    {t(`chapterTypes.${ct.value}.description`)}
                  </div>
                </div>
              </button>
            )
          })}
        </div>
      </div>

      {/* Type-specific editor */}
      <Card data-tour="chapter-editor-blocks" className="mb-6">
        <CardContent className="space-y-4 p-5">
          {chapterType === "reading" && (
            <ChapterBlockEditor chapterId={chapter.id} />
          )}

          {(chapterType === "quiz" || chapterType === "exam") && (
            <QuizEditor chapterId={chapter.id} chapterType={chapterType} />
          )}

          {chapterType === "assignment" && (
            <AssignmentEditor chapterId={chapter.id} />
          )}
        </CardContent>
      </Card>

      {/* Inline save button (always visible). When the chapter is dirty,
          a sticky reminder also appears at the bottom of the viewport. */}
      <div className="flex items-center gap-3">
        <Button onClick={save} disabled={saving}>
          {saving ? (
            <Loader2 className="h-4 w-4 mr-2 animate-spin" strokeWidth={1.75} aria-hidden />
          ) : (
            <Save className="h-4 w-4 mr-2" strokeWidth={1.75} aria-hidden />
          )}
          {saving ? t("chapterEditor.saving") : t("chapterEditor.save")}
        </Button>
        <span className="text-xs text-muted-foreground">{t("chapterEditor.saveHint")}</span>
      </div>

      {/* Sticky save bar — only renders while there are unsaved
          changes. The pulsing warning dot is the visual cue, the
          ``aria-label`` on the parent card is the screen-reader cue
          (announced via ``aria-live="polite"`` on first transition to
          dirty). Inline text shows the Ctrl+S shortcut. */}
      {isDirty && (
        <div className="pointer-events-none fixed inset-x-0 bottom-0 z-40 flex justify-center px-4 pb-[calc(env(safe-area-inset-bottom)+1rem)] sm:pb-6">
          <Card
            role="status"
            aria-live="polite"
            aria-label={t("chapterEditor.unsavedChanges")}
            className="pointer-events-auto animate-fade-in w-full max-w-2xl bg-card/95 shadow-lg backdrop-blur supports-[backdrop-filter]:bg-card/85"
          >
            <CardContent className="flex items-center gap-3 px-4 py-3">
              <span
                className="relative flex h-2 w-2 shrink-0"
                aria-hidden
              >
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-warning/60" />
                <span className="relative inline-flex h-2 w-2 rounded-full bg-warning" />
              </span>
              <span className="flex-1 text-xs text-muted-foreground sm:text-sm">
                <span className="font-medium text-foreground">
                  {t("chapterEditor.unsavedChanges")}
                </span>
                <span className="mx-1.5 opacity-40">·</span>
                {t("chapterEditor.saveHint")}
              </span>
              <Button
                type="button"
                size="sm"
                onClick={save}
                disabled={saving}
              >
                {saving ? (
                  <Loader2 className="h-3.5 w-3.5 mr-1.5 animate-spin" strokeWidth={1.75} aria-hidden />
                ) : (
                  <Save className="h-3.5 w-3.5 mr-1.5" strokeWidth={1.75} aria-hidden />
                )}
                {saving ? t("chapterEditor.saving") : t("chapterEditor.save")}
              </Button>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  )
}
