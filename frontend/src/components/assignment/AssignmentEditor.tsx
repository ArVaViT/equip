import { useEffect, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { Button } from "@/components/ui/button"
import { FileText, Loader2, Plus } from "lucide-react"
import { useConfirm } from "@/components/ui/alert-dialog"
import { coursesService } from "@/services/courses"
import { toast } from "@/lib/toast"
import type { Assignment } from "@/types"
import {
  AssignmentForm,
  AssignmentItem,
  EMPTY_ASSIGNMENT_FORM,
  formStateToPayload,
  type AssignmentFormState,
} from "./editor"

interface AssignmentEditorProps {
  chapterId: string
  /** Needed by the rubric editor: rubrics belong to a course and are reused
   *  across the assignments in it. */
  courseId: string
  onAssignmentCreated?: (assignmentId: string) => void
  /** Told whenever the new-assignment form holds something not yet sent. */
  onDirtyChange?: (dirty: boolean) => void
  /** The lesson's name: the first assignment starts with it. */
  defaultTitle?: string
}

/**
 * Teacher-facing list of assignments for a chapter. Thin orchestrator:
 * owns the list + "create" form state, and delegates each row (with its
 * edit form and submissions grader) to `AssignmentItem`.
 */
export default function AssignmentEditor({
  chapterId,
  courseId,
  onAssignmentCreated,
  onDirtyChange,
  defaultTitle = "",
}: AssignmentEditorProps) {
  const confirm = useConfirm()
  const { t } = useTranslation()
  // Read when a lesson opens, not followed (see useQuizDraft).
  const defaultTitleRef = useRef(defaultTitle)
  useEffect(() => {
    defaultTitleRef.current = defaultTitle
  }, [defaultTitle])
  const [assignments, setAssignments] = useState<Assignment[]>([])
  const [loading, setLoading] = useState(true)
  const [fetchError, setFetchError] = useState(false)

  const [form, setForm] = useState<AssignmentFormState>(EMPTY_ASSIGNMENT_FORM)
  const [creating, setCreating] = useState(false)
  const [showCreate, setShowCreate] = useState(false)
  // The form as it was opened, to tell typing from looking.
  const [formBaseline, setFormBaseline] = useState(JSON.stringify(EMPTY_ASSIGNMENT_FORM))
  const dirty = showCreate && JSON.stringify(form) !== formBaseline
  useEffect(() => {
    onDirtyChange?.(dirty)
  }, [dirty, onDirtyChange])
  useEffect(() => () => onDirtyChange?.(false), [onDirtyChange])

  const openCreate = (title: string) => {
    const start = { ...EMPTY_ASSIGNMENT_FORM, title }
    setForm(start)
    setFormBaseline(JSON.stringify(start))
    setShowCreate(true)
  }

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setFetchError(false)
    // Editor-only fetch so the form binds to source-language `title` /
    // `description` columns regardless of UI locale. Without this a
    // teacher in EN UI editing their RU assignment would see the EN
    // translation in the form and a PATCH would overwrite the source.
    coursesService
      .getChapterAssignmentsForEdit(chapterId)
      .then((data) => {
        if (cancelled) return
        setAssignments(data)
        // An assignment lesson with no assignment has one thing to do:
        // write it. The form opens with the lesson's name instead of an
        // empty list and a small "New assignment" button to find.
        if (data.length === 0) {
          const start = { ...EMPTY_ASSIGNMENT_FORM, title: defaultTitleRef.current }
          setForm(start)
          setFormBaseline(JSON.stringify(start))
          setShowCreate(true)
        }
      })
      .catch(() => {
        if (!cancelled) setFetchError(true)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [chapterId])

  const handleCreate = async () => {
    if (!form.title.trim()) {
      toast({ title: t("assignmentEditor.validation.titleRequired"), variant: "destructive" })
      return
    }
    setCreating(true)
    try {
      const a = await coursesService.createAssignment({
        chapter_id: chapterId,
        ...formStateToPayload(form),
      })
      setAssignments((prev) => [...prev, a])
      onAssignmentCreated?.(a.id)
      setForm(EMPTY_ASSIGNMENT_FORM)
      setFormBaseline(JSON.stringify(EMPTY_ASSIGNMENT_FORM))
      setShowCreate(false)
      toast({ title: t("assignmentEditor.toast.created"), variant: "success" })
    } catch {
      toast({ title: t("assignmentEditor.toast.createFailed"), variant: "destructive" })
    } finally {
      setCreating(false)
    }
  }

  const handleDelete = async (id: string) => {
    const ok = await confirm({
      title: t("assignmentEditor.confirmDelete.title"),
      description: t("assignmentEditor.confirmDelete.description"),
      confirmLabel: t("assignmentEditor.confirmDelete.confirm"),
      tone: "destructive",
    })
    if (!ok) return
    try {
      await coursesService.deleteAssignment(id)
      setAssignments((prev) => prev.filter((a) => a.id !== id))
      toast({ title: t("assignmentEditor.toast.deleted"), variant: "success" })
    } catch {
      toast({ title: t("assignmentEditor.toast.deleteFailed"), variant: "destructive" })
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-8">
        <Loader2 className="h-5 w-5 animate-spin text-ink-muted" strokeWidth={1.75} />
      </div>
    )
  }

  if (fetchError) {
    return (
      <p className="text-sm text-destructive py-4 text-center">
        {t("assignmentEditor.loadFailed")}
      </p>
    )
  }

  return (
    <div className="space-y-4 mt-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <FileText className="h-4 w-4 text-ink-muted" strokeWidth={1.75} />
          <span className="text-sm font-medium">
            {t("assignmentEditor.heading", { count: assignments.length })}
          </span>
        </div>
        <Button
          variant="outline"
          size="sm"
          className="h-7 text-xs"
          onClick={() => (showCreate ? setShowCreate(false) : openCreate(""))}
        >
          <Plus className="h-3 w-3 mr-1" strokeWidth={1.75} />
          {t("assignmentEditor.newAssignment")}
        </Button>
      </div>

      {showCreate && (
        <AssignmentForm
          value={form}
          onChange={setForm}
          onSubmit={handleCreate}
          onCancel={() => setShowCreate(false)}
          submitting={creating}
          mode="create"
        />
      )}

      {assignments.map((a) => (
        <AssignmentItem
          key={a.id}
          assignment={a}
          courseId={courseId}
          onDelete={handleDelete}
          onUpdate={(updated) =>
            setAssignments((prev) => prev.map((x) => (x.id === updated.id ? updated : x)))
          }
        />
      ))}

      {assignments.length === 0 && !showCreate && (
        <div className="text-center py-6 border border-dashed rounded-md text-sm text-ink-muted">
          {t("assignmentEditor.empty")}
        </div>
      )}
    </div>
  )
}
