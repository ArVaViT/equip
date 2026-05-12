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
import { chapterSchema } from "@/lib/validations/course"
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

const EDITOR_OPTIONS = CHAPTER_TYPES.map((value) => {
  const meta = CHAPTER_TYPE_META[value]
  return {
    value,
    label: meta.label,
    desc: meta.description,
    icon: meta.icon,
  }
})

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

  const load = useCallback(async (signal?: { cancelled: boolean }) => {
    if (!courseId || !moduleId || !chapterId) return
    setLoading(true)
    try {
      const mod = await coursesService.getModule(courseId, moduleId)
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
    const validation = chapterSchema.safeParse({
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
    <div className="container mx-auto px-4 py-8 max-w-4xl">
      {/* Breadcrumb */}
      <div className="mb-6 flex items-center gap-2 text-sm text-muted-foreground">
        <Link to="/teacher" className="hover:text-foreground transition-colors">
          {t("chapterEditor.breadcrumb.myCourses")}
        </Link>
        <ChevronRight className="h-3.5 w-3.5" />
        <Link
          to={`/teacher/courses/${courseId}`}
          className="hover:text-foreground transition-colors"
        >
          {t("chapterEditor.breadcrumb.course")}
        </Link>
        <ChevronRight className="h-3.5 w-3.5" />
        <Link
          to={`/teacher/courses/${courseId}/modules/${moduleId}/edit`}
          className="hover:text-foreground transition-colors"
        >
          {moduleName}
        </Link>
        <ChevronRight className="h-3.5 w-3.5" />
        <span className="text-foreground font-medium truncate max-w-[200px]">
          {title || t("chapterEditor.chapterFallback")}
        </span>
      </div>

      {/* Back button + title row */}
      <div className="flex items-center gap-3 mb-6">
        <Button
          variant="ghost"
          size="sm"
          className="shrink-0"
          onClick={async () => {
            if (isDirty) {
              const ok = await confirm({
                title: t("chapterEditor.leaveConfirm.title"),
                description: t("chapterEditor.leaveConfirm.description"),
                confirmLabel: t("chapterEditor.leaveConfirm.confirm"),
                tone: "destructive",
              })
              if (!ok) return
            }
            navigate(`/teacher/courses/${courseId}/modules/${moduleId}/edit`)
          }}
        >
          <ArrowLeft className="h-4 w-4 mr-1" />
          {t("chapterEditor.back")}
        </Button>
        <Input
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          className="font-serif text-2xl font-bold border-none shadow-none hover:border-border/50 hover:shadow-sm focus-visible:ring-1 h-auto py-1 px-2 flex-1"
          placeholder={t("chapterEditor.titlePlaceholder")}
        />
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
                onClick={() => setChapterType(ct.value)}
                className={`flex items-start gap-3 rounded-lg border-2 p-4 text-left transition-all ${
                  selected
                    ? "border-primary bg-primary/5 shadow-sm"
                    : "border-border hover:border-primary/30 hover:bg-muted/40"
                }`}
              >
                <Icon
                  className={`h-5 w-5 mt-0.5 shrink-0 ${
                    selected ? "text-primary" : "text-muted-foreground"
                  }`}
                />
                <div>
                  <div
                    className={`text-sm font-medium ${
                      selected ? "text-primary" : ""
                    }`}
                  >
                    {ct.label}
                  </div>
                  <div className="text-xs text-muted-foreground mt-0.5">
                    {ct.desc}
                  </div>
                </div>
              </button>
            )
          })}
        </div>
      </div>

      {/* Type-specific editor */}
      <Card className="mb-6">
        <CardContent className="p-6 space-y-4">
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

      {/* Save button */}
      <div className="flex items-center gap-3">
        <Button onClick={save} disabled={saving}>
          {saving ? (
            <Loader2 className="h-4 w-4 mr-2 animate-spin" />
          ) : (
            <Save className="h-4 w-4 mr-2" />
          )}
          {saving ? t("chapterEditor.saving") : t("chapterEditor.save")}
        </Button>
        <span className="text-xs text-muted-foreground">{t("chapterEditor.saveHint")}</span>
      </div>
    </div>
  )
}
