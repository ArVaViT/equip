import { useEffect, useState, useCallback, useRef } from "react"
import { useParams, Link, useNavigate } from "react-router-dom"
import { useTranslation } from "react-i18next"
import { getErrorDetail } from "@/lib/errorDetail"
import { Card, CardContent } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import ChapterBlockEditor from "@/components/editor/ChapterBlockEditor"
import QuizEditor from "@/components/quiz/QuizEditor"
import AssignmentEditor from "@/components/assignment/AssignmentEditor"
import { coursesService } from "@/services/courses"
import type { Chapter } from "@/types"
import { toast } from "@/lib/toast"
import { makeChapterSchema } from "@/lib/validations/course"
import { useConfirm } from "@/components/ui/alert-dialog"
import {
  AlertCircle, ArrowLeft, Check, ChevronDown, ChevronRight, Eye, Info, Loader2,
} from "lucide-react"
import { cn } from "@/lib/utils"
import {
  CHAPTER_TYPES,
  CHAPTER_TYPE_DESCRIPTION_KEYS,
  CHAPTER_TYPE_LABEL_KEYS,
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

type ChapterUpdatePayload = Parameters<typeof coursesService.updateCourseChapter>[2]

/**
 * Which editor a chapter type opens. Quiz and exam share one, so moving
 * between them keeps the questions on screen; every other move swaps the
 * editor out and hides what was written in the previous one.
 */
type EditorFamily = "reading" | "quiz" | "assignment"
const EDITOR_FAMILY: Record<ChapterType, EditorFamily> = {
  reading: "reading",
  quiz: "quiz",
  exam: "quiz",
  assignment: "assignment",
}

/**
 * Does the editor for ``type`` have anything in it for this chapter?
 * Asked only at the moment of switching, so the page does not pay three
 * extra requests on every open. A probe that fails answers "yes": asking
 * one unnecessary question is cheaper than letting a lesson vanish
 * without a word.
 */
async function editorHasContent(type: ChapterType, chapterId: string): Promise<boolean> {
  try {
    switch (EDITOR_FAMILY[type]) {
      case "reading":
        return (await coursesService.getChapterBlocksForEdit(chapterId)).length > 0
      case "quiz":
        return (await coursesService.getChapterQuizForEdit(chapterId)) !== null
      case "assignment":
        return (await coursesService.getChapterAssignmentsForEdit(chapterId)).length > 0
    }
  } catch {
    return true
  }
}

/**
 * What the header says about saving. One place, one sentence — the page
 * saves by itself, so the only thing a teacher needs is to know it did, or
 * that it did not and can be tried again.
 */
function SaveStatus({
  state,
  detail,
  onRetry,
}: {
  state: "idle" | "saving" | "saved" | "error" | "needsTitle"
  detail?: string
  onRetry: () => void
}) {
  const { t } = useTranslation()
  if (state === "idle") return null
  return (
    <span role="status" aria-live="polite" className="flex shrink-0 items-center gap-1.5 text-xs text-ink-muted">
      {state === "saving" && (
        <>
          <Loader2 className="h-3.5 w-3.5 animate-spin" strokeWidth={1.75} aria-hidden />
          <span className="max-sm:sr-only">{t("chapterEditor.status.saving")}</span>
        </>
      )}
      {state === "saved" && (
        <>
          <Check className="h-3.5 w-3.5 text-success" strokeWidth={1.75} aria-hidden />
          <span className="max-sm:sr-only">{t("chapterEditor.status.saved")}</span>
        </>
      )}
      {state === "needsTitle" && (
        <>
          <AlertCircle className="h-3.5 w-3.5 text-warning" strokeWidth={1.75} aria-hidden />
          <span>{t("chapterEditor.status.needsTitle")}</span>
        </>
      )}
      {state === "error" && (
        <>
          <AlertCircle className="h-3.5 w-3.5 text-destructive" strokeWidth={1.75} aria-hidden />
          <span className="text-destructive" title={detail || undefined}>{t("chapterEditor.status.failed")}</span>
          <button type="button" onClick={onRetry} className="font-medium text-ink underline underline-offset-2">
            {t("chapterEditor.status.retry")}
          </button>
        </>
      )}
    </span>
  )
}

export default function ChapterEditor() {
  // The older address also carries a ``moduleId``; this page no longer
  // reads it. The lesson's own ``module_id`` is the authority either way,
  // so a link written before the lesson was moved still lands on the
  // lesson and still shows where it actually sits now.
  const { courseId, chapterId } = useParams<{
    courseId: string
    chapterId: string
  }>()
  const navigate = useNavigate()
  const confirm = useConfirm()
  const { t } = useTranslation()

  const [chapter, setChapter] = useState<Chapter | null>(null)
  const [loading, setLoading] = useState(true)
  /** The one save state on the page. The lesson's name and type save
   *  themselves; this is what the header says about it. There used to be
   *  a "Save lesson" button that saved only those two fields while the
   *  text saved itself and the quiz had its own button — three ways to
   *  save, and no way to tell which one a change needed. */
  const [status, setStatus] = useState<"idle" | "saving" | "saved" | "error">("idle")
  /** The quiz or assignment editor below holds work it has not sent. */
  const [childDirty, setChildDirty] = useState({ quiz: false, assignment: false })
  const onQuizDirty = useCallback(
    (dirty: boolean) => setChildDirty((p) => (p.quiz === dirty ? p : { ...p, quiz: dirty })),
    [],
  )
  const onAssignmentDirty = useCallback(
    (dirty: boolean) => setChildDirty((p) => (p.assignment === dirty ? p : { ...p, assignment: dirty })),
    [],
  )
  /** Published course: an edit waits for every language (by design). */
  const [coursePublished, setCoursePublished] = useState(false)
  const [typePickerOpen, setTypePickerOpen] = useState(false)
  /** The course's name for the breadcrumb, which read a bare «Course». */
  const [courseTitle, setCourseTitle] = useState("")
  /** Why the last save failed, for the status's tooltip. */
  const [errorDetail, setErrorDetail] = useState("")

  const [title, setTitle] = useState("")
  const [chapterType, setChapterType] = useState<ChapterType>("reading")
  /** The module around this lesson, when there is one. ``null`` is not a
   *  stand-in for "not loaded" — it is the answer for a lesson that is in
   *  no module, and the breadcrumb renders one crumb fewer. */
  const [group, setGroup] = useState<{ id: string; title: string | null } | null>(null)
  const [isDirty, setIsDirty] = useState(false)

  useUserTour({
    tourId: "chapter-editor-v1",
    steps: chapterEditorSteps(t),
    ready: !loading && chapter !== null,
  })

  // Read through a ref: with ``t`` in its dependencies, switching the
  // interface language mid-edit re-ran the load, remounted the quiz or
  // assignment editor and dropped its unsaved draft without a word.
  const tRef = useRef(t)
  useEffect(() => {
    tRef.current = t
  }, [t])
  const load = useCallback(async (signal?: { cancelled: boolean }) => {
    if (!courseId || !chapterId) return
    setLoading(true)
    try {
      // The lesson by its own id. This used to fetch the module around it
      // and pick the lesson out of that list, which asks for a module the
      // lesson need not have and had no answer at all for one written
      // straight into the course. Editor-only, so the title renders in the
      // source language whatever the viewer's UI locale: what you see is
      // what you would PATCH back.
      const ch = await coursesService.getChapterForEdit(courseId, chapterId)
      if (signal?.cancelled) return
      // For the note about languages and the breadcrumb's course name; the
      // page works without it (the crumb then says «Course»).
      setCourseTitle("")
      void coursesService
        .getCourseForEdit(courseId)
        .then((c) => {
          if (signal?.cancelled) return
          setCoursePublished(c.status !== "draft")
          setCourseTitle(c.title)
        })
        .catch(() => undefined)
      setChapter(ch)
      setTitle(ch.title)
      const resolvedType = normalizeChapterType(ch.chapter_type)
      setChapterType(resolvedType)
      setInitialSnapshot(JSON.stringify({
        title: ch.title,
        chapterType: resolvedType,
      }))
      setIsDirty(false)
      if (!ch.module_id) {
        setGroup(null)
        return
      }
      // A second round-trip, and only for a grouped lesson: the breadcrumb
      // wants the module's name and the lesson row carries only its id.
      try {
        const mod = await coursesService.getModuleForEdit(courseId, ch.module_id)
        if (signal?.cancelled) return
        setGroup({ id: mod.id, title: mod.title })
      } catch {
        // One breadcrumb crumb is not worth failing the page over — keep
        // the link, lose only the name.
        if (!signal?.cancelled) {
          // ``null``: the generic word is picked at render, in the language
          // shown then, not frozen at load.
          setGroup({ id: ch.module_id, title: null })
        }
      }
    } catch {
      if (signal?.cancelled) return
      toast({ title: tRef.current("chapterEditor.toast.loadFailed"), variant: "destructive" })
      navigate(`/teacher/courses/${courseId}`)
    } finally {
      if (!signal?.cancelled) setLoading(false)
    }
  }, [courseId, chapterId, navigate])

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

  const childUnsaved = childDirty.quiz || childDirty.assignment
  const unsaved = isDirty || childUnsaved || status === "saving"

  useEffect(() => {
    if (!unsaved) return
    const handleBeforeUnload = (e: BeforeUnloadEvent) => {
      e.preventDefault()
    }
    window.addEventListener("beforeunload", handleBeforeUnload)
    return () => window.removeEventListener("beforeunload", handleBeforeUnload)
  }, [unsaved])

  const save = useCallback(async ({ quiet = false }: { quiet?: boolean } = {}): Promise<boolean> => {
    if (!courseId || !chapterId || !title.trim()) return false
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
      // The header says so (status "error", the reason on hover). A toast
      // only when the teacher asked — Ctrl+S, "Retry" — not after every
      // pause in typing.
      const first = validation.error.issues[0]
      const message = first?.message ?? t("chapterEditor.toast.invalidData")
      setErrorDetail(message)
      setStatus("error")
      if (!quiet) toast({ title: message, variant: "destructive" })
      return false
    }
    setStatus("saving")
    try {
      const payload: ChapterUpdatePayload = {
        title: title.trim(),
        chapter_type: chapterType,
      }

      // No ``module_id`` key in the payload, which the route reads as
      // "leave the grouping alone". An explicit ``null`` here would lift
      // every saved lesson out of its module.
      await coursesService.updateCourseChapter(courseId, chapterId, payload)
      // The snapshot is what was sent, untrimmed as typed: a trailing
      // space the teacher is still typing must not read as a new change.
      setInitialSnapshot(JSON.stringify({ title, chapterType }))
      setIsDirty(false)
      setStatus("saved")
      return true
    } catch (error: unknown) {
      const detail = getErrorDetail(error) || t("chapterEditor.unknownError")
      // Said once in the header («Не сохранено», the reason on hover); a
      // toast only when the teacher asked. While the server kept failing,
      // every pause in typing raised another one.
      if (!quiet) {
        toast({
          title: t("chapterEditor.toast.saveFailed", { detail }),
          variant: "destructive",
        })
      }
      setErrorDetail(detail)
      setStatus("error")
      return false
    }
  }, [courseId, chapterId, title, chapterType, t])

  // Name and type save themselves, a moment after the last keystroke —
  // the way the course's and the module's names already did.
  useEffect(() => {
    if (!isDirty || !title.trim() || status === "error") return
    const id = window.setTimeout(() => void save({ quiet: true }), 800)
    return () => window.clearTimeout(id)
  }, [isDirty, title, chapterType, status, save])

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "s") {
        // Habit, not a requirement: everything saves itself. The browser's
        // "save page" dialog is the one thing this must not open.
        e.preventDefault()
        if (isDirty) void save()
      }
    }
    document.addEventListener("keydown", handleKeyDown)
    return () => document.removeEventListener("keydown", handleKeyDown)
  }, [save, isDirty])

  // Switching the tile from "Reading" to "Quiz" used to swap the editor
  // instantly. Nothing is deleted — the blocks stay in their table and
  // come back the moment the tile is switched back — but the teacher
  // watching a written lesson disappear has no way of knowing that.
  // So when the current editor holds anything, ask first, and say in
  // plain words that the work is kept.
  const switchingTypeRef = useRef(false)
  const changeChapterType = useCallback(
    async (next: ChapterType) => {
      if (!chapter || next === chapterType || switchingTypeRef.current) return
      // Held for the whole decision, dialogs included: two quick picks
      // used to open two dialogs on top of each other.
      switchingTypeRef.current = true
      try {
        if (EDITOR_FAMILY[next] === EDITOR_FAMILY[chapterType]) {
          // Quiz ↔ exam keeps the editor but reloads the quiz from the
          // server, so questions typed and not saved would go without a word.
          if (childDirty.quiz) {
            const ok = await confirm({
              title: t("chapterEditor.typeChangeUnsaved.title"),
              description: t("chapterEditor.typeChangeUnsaved.description"),
              confirmLabel: t("chapterEditor.typeChangeUnsaved.confirm"),
              tone: "destructive",
            })
            if (!ok) return
          }
        } else if (await editorHasContent(chapterType, chapter.id)) {
          const ok = await confirm({
            title: t("chapterEditor.typeChangeConfirm.title"),
            description: t("chapterEditor.typeChangeConfirm.description", {
              from: t(CHAPTER_TYPE_LABEL_KEYS[chapterType]),
              to: t(CHAPTER_TYPE_LABEL_KEYS[next]),
            }),
            confirmLabel: t("chapterEditor.typeChangeConfirm.confirm"),
          })
          if (!ok) return
        }
        // A new edit is a new attempt, as with the title: autosave resumes
        // after a failure instead of holding the new type back.
        setStatus((s) => (s === "error" ? "idle" : s))
        setChapterType(next)
      } finally {
        switchingTypeRef.current = false
      }
    },
    [chapter, chapterType, childDirty.quiz, confirm, t],
  )

  // Shared dirty-check used by the Back button and every breadcrumb
  // link. Pre-fix, only the Back button asked before discarding work;
  // a click on any breadcrumb crumb silently navigated away. Three of
  // them — easy to miss when you've just typed two paragraphs.
  // A name still waiting for its save goes now; only a quiz or an
  // assignment that has not been sent needs the teacher's decision —
  // those are the work that would be lost (they used to be lost silently).
  const guardedNavigate = useCallback(
    async (to: string) => {
      if (isDirty && title.trim() && !(await save())) {
        const ok = await confirm({
          title: t("chapterEditor.leaveConfirm.title"),
          description: t("chapterEditor.leaveConfirm.description"),
          confirmLabel: t("chapterEditor.leaveConfirm.confirm"),
          tone: "destructive",
        })
        if (!ok) return
      }
      if (childUnsaved) {
        const ok = await confirm({
          title: t("chapterEditor.leaveUnsavedWork.title"),
          description: t("chapterEditor.leaveUnsavedWork.description"),
          confirmLabel: t("chapterEditor.leaveUnsavedWork.confirm"),
          tone: "destructive",
        })
        if (!ok) return
      }
      navigate(to)
    },
    [childUnsaved, confirm, isDirty, navigate, save, t, title],
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

  // Route always supplies these, but useParams types them optional. Narrow
  // once here so children (e.g. ChapterBlockEditor) get a concrete courseId.
  if (!courseId || !chapterId) return null

  // Up one level: the module when the lesson is in one, the course when it
  // is not. Both the Back button and the "not found" escape hatch use it,
  // so a lesson written straight into the course leads back to the course
  // rather than to a module that was never there.
  const CurrentTypeIcon = CHAPTER_TYPE_META[chapterType].icon

  const upHref = group
    ? `/teacher/courses/${courseId}/modules/${group.id}/edit`
    : `/teacher/courses/${courseId}`

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
            onClick={() => navigate(`/teacher/courses/${courseId}`)}
          >
            {t("chapterEditor.notFound.backToCourse")}
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
      <div className="mb-6 flex items-center gap-2 text-sm text-ink-muted">
        <Link
          to="/teacher"
          onClick={(e) => handleNavClick(e, "/teacher")}
          className="hidden shrink-0 whitespace-nowrap transition-colors hover:text-ink sm:inline"
        >
          {t("chapterEditor.breadcrumb.myCourses")}
        </Link>
        <ChevronRight className="hidden h-3.5 w-3.5 sm:inline-block" strokeWidth={1.75} />
        <Link
          to={`/teacher/courses/${courseId}`}
          onClick={(e) => handleNavClick(e, `/teacher/courses/${courseId}`)}
          className="hidden max-w-[16rem] truncate transition-colors hover:text-ink sm:inline"
        >
          {courseTitle || t("chapterEditor.breadcrumb.course")}
        </Link>
        {/* The module crumb only when there is a module. A lesson that
            sits straight in the course reads
            «My Courses › Course › Lesson», with nothing invented to fill
            the gap. */}
        {group && (
          <>
            <ChevronRight className="hidden h-3.5 w-3.5 sm:inline-block" strokeWidth={1.75} />
            <Link
              to={upHref}
              onClick={(e) => handleNavClick(e, upHref)}
              className="min-w-0 truncate transition-colors hover:text-ink"
            >
              {group.title ?? t("chapterEditor.moduleFallback")}
            </Link>
          </>
        )}
        <ChevronRight className="h-3.5 w-3.5 shrink-0" strokeWidth={1.75} />
        <span className="min-w-0 truncate font-medium text-ink sm:max-w-[200px]">
          {title || t("chapterEditor.chapterFallback")}
        </span>
      </div>

      {/* Back button + title row */}
      <div data-tour="chapter-editor-header" className="mb-6 flex flex-wrap items-center gap-x-3 gap-y-2">
        <Button
          variant="ghost"
          size="sm"
          className="shrink-0"
          onClick={() => void guardedNavigate(upHref)}
        >
          <ArrowLeft className="h-4 w-4 mr-1" strokeWidth={1.75} />
          {t("chapterEditor.back")}
        </Button>
        {/* Render the editable title as a real ``<h1>`` so the page
            outline has the chapter name at heading-level-1, and add
            ``aria-label`` so the input still has an accessible name
            even though its visual label is implicit. */}
        {/* Its own line on a phone: between "Back" and the eye it had a
            third of the width and cut the name to «Урок 1. Не кни». */}
        <h1 className="order-last m-0 w-full sm:order-none sm:w-auto sm:flex-1">
          <Input
            value={title}
            onChange={(e) => {
              setTitle(e.target.value)
              // A new edit is a new attempt: autosave resumes after a failure.
              if (status === "error") setStatus("idle")
            }}
            aria-label={t("chapterEditor.editTitleAria")}
            // `sm:text-2xl` too: the field's own `sm:text-sm` won at every
            // width from 640px, and the lesson's name sat in the header at
            // 14px (found 2026-09-29).
            className="h-auto w-full border-none bg-transparent px-2 py-1 font-serif text-xl font-bold tracking-tight shadow-none hover:border-edge hover:shadow-sm focus-visible:ring-1 sm:text-2xl"
            placeholder={t("chapterEditor.titlePlaceholder")}
          />
        </h1>
        <span className="ml-auto flex items-center gap-2 sm:ml-0">
        <SaveStatus
          state={
            status === "error"
              ? "error"
              : !title.trim()
                ? "needsTitle"
                : isDirty || status === "saving"
                  ? "saving"
                  : status
          }
          detail={errorDetail}
          onRetry={() => {
            setStatus("idle")
            void save()
          }}
        />
        {/* The lesson as a student reads it, in a new tab so the editor
            stays where it was. From the course page only, until now. */}
        <Button asChild variant="ghost" size="sm" className="shrink-0">
          <a href={`/courses/${courseId}/chapters/${chapter.id}`} target="_blank" rel="noopener">
            <Eye className="h-4 w-4 sm:mr-1.5" strokeWidth={1.75} aria-hidden />
            <span className="max-sm:sr-only">{t("chapterEditor.preview")}</span>
          </a>
        </Button>
        </span>
      </div>

      {coursePublished && (
        <p className="-mt-3 mb-5 flex items-start gap-2 text-xs text-ink-muted">
          <Info className="mt-px h-3.5 w-3.5 shrink-0" strokeWidth={1.75} aria-hidden />
          {t("chapterEditor.publishedNote")}
        </p>
      )}

      {/* Lesson type — one line. It is chosen when the lesson is created;
          a grid of four large cards at the top of every lesson asked the
          question again each time the lesson was opened. */}
      <div className="mb-4">
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <span className="text-ink-muted">{t("chapterEditor.chapterType")}:</span>
          <span className="inline-flex items-center gap-1.5 rounded-full bg-muted px-2.5 py-1 font-medium text-ink">
            <CurrentTypeIcon className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
            {t(CHAPTER_TYPE_LABEL_KEYS[chapterType])}
          </span>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="h-7 px-2 text-xs text-ink-muted"
            aria-expanded={typePickerOpen}
            onClick={() => setTypePickerOpen((open) => !open)}
          >
            {t("chapterEditor.changeType")}
            <ChevronDown
              className={cn("ml-1 h-3.5 w-3.5 transition-transform", typePickerOpen && "rotate-180")}
              strokeWidth={1.75}
              aria-hidden
            />
          </Button>
        </div>
        {typePickerOpen && (
          <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
            {EDITOR_OPTIONS.map((ct) => {
              const Icon = ct.icon
              const selected = chapterType === ct.value
              return (
                <button
                  key={ct.value}
                  type="button"
                  onClick={() => {
                    setTypePickerOpen(false)
                    void changeChapterType(ct.value)
                  }}
                  aria-pressed={selected}
                  className={`flex items-start gap-3 rounded-lg border p-4 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 ${
                    selected
                      ? "border-brand bg-brand/[0.08] ring-1 ring-primary/40 dark:bg-brand/15"
                      : "border-edge hover:border-brand/30 hover:bg-muted/40"
                  }`}
                >
                  <Icon
                    className={`h-5 w-5 mt-0.5 shrink-0 ${selected ? "text-brand" : "text-ink-muted"}`}
                    strokeWidth={1.75}
                    aria-hidden
                  />
                  <div>
                    <div className={`text-sm font-medium ${selected ? "text-brand" : ""}`}>
                      {t(CHAPTER_TYPE_LABEL_KEYS[ct.value])}
                    </div>
                    <div className="text-xs text-ink-muted mt-0.5">
                      {t(CHAPTER_TYPE_DESCRIPTION_KEYS[ct.value])}
                    </div>
                  </div>
                </button>
              )
            })}
          </div>
        )}
      </div>

      {/* Type-specific editor */}
      <Card data-tour="chapter-editor-blocks" className="mb-6">
        <CardContent className="space-y-4 p-5">
          {chapterType === "reading" && (
            <ChapterBlockEditor courseId={courseId} chapterId={chapter.id} />
          )}

          {(chapterType === "quiz" || chapterType === "exam") && (
            <QuizEditor
              chapterId={chapter.id}
              chapterType={chapterType}
              defaultTitle={title.trim()}
              onDirtyChange={onQuizDirty}
            />
          )}

          {chapterType === "assignment" && (
            <AssignmentEditor
              chapterId={chapter.id}
              courseId={courseId}
              defaultTitle={title.trim()}
              onDirtyChange={onAssignmentDirty}
            />
          )}
        </CardContent>
      </Card>
    </div>
  )
}
