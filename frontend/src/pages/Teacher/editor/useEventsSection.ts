import { useCallback, useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { coursesService } from "@/services/courses"
import { toast } from "@/lib/toast"
import type { CourseEvent } from "@/types"
import type { useConfirm } from "@/components/ui/alert-dialog"
import { EMPTY_EVENT_FORM, type EventFormState } from "./types"

type Confirm = ReturnType<typeof useConfirm>

interface EventsSection {
  events: CourseEvent[]
  form: EventFormState
  setForm: (v: EventFormState) => void
  editingId: string | null
  saving: boolean
  startEdit: (ev: CourseEvent) => void
  save: () => Promise<void>
  remove: (id: string) => Promise<void>
  resetForm: () => void
}

/**
 * Owns the "Events" modal state: list, the inline edit form, and
 * create/update/delete handlers.
 */
export function useEventsSection(
  courseId: string | undefined,
  confirm: Confirm,
): EventsSection {
  const { t } = useTranslation()
  const [events, setEvents] = useState<CourseEvent[]>([])
  const [form, setForm] = useState<EventFormState>(EMPTY_EVENT_FORM)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (!courseId) return
    let cancelled = false
    coursesService
      .getCourseEvents(courseId)
      .then((e) => {
        if (!cancelled) setEvents(e)
      })
      .catch(() => {
        if (!cancelled) setEvents([])
      })
    return () => {
      cancelled = true
    }
  }, [courseId])

  const resetForm = useCallback(() => {
    setForm(EMPTY_EVENT_FORM)
    setEditingId(null)
  }, [])

  const startEdit = useCallback((ev: CourseEvent) => {
    setForm({
      title: ev.title,
      description: ev.description ?? "",
      event_type: ev.event_type,
      event_date: ev.event_date.slice(0, 16),
    })
    setEditingId(ev.id)
  }, [])

  const save = useCallback(async () => {
    if (!courseId || !form.title.trim() || !form.event_date) return
    setSaving(true)
    const payload = {
      title: form.title.trim(),
      description: form.description.trim() || undefined,
      event_type: form.event_type,
      event_date: new Date(form.event_date).toISOString(),
    }
    try {
      if (editingId) {
        const updated = await coursesService.updateCourseEvent(courseId, editingId, payload)
        setEvents((p) => p.map((ev) => (ev.id === editingId ? updated : ev)))
        toast({ title: t("teacherEditor.toast.eventUpdated"), variant: "success" })
      } else {
        const created = await coursesService.createCourseEvent(courseId, payload)
        setEvents((p) => [...p, created])
        toast({ title: t("teacherEditor.toast.eventCreated"), variant: "success" })
      }
      resetForm()
    } catch {
      toast({ title: t("teacherEditor.toast.eventSaveFailed"), variant: "destructive" })
    } finally {
      setSaving(false)
    }
  }, [courseId, form, editingId, resetForm, t])

  const remove = useCallback(
    async (id: string) => {
      if (!courseId) return
      const ok = await confirm({
        title: t("teacherEditor.confirm.deleteEventTitle"),
        confirmLabel: t("teacherEditor.confirm.deleteEventAction"),
        tone: "destructive",
      })
      if (!ok) return
      try {
        await coursesService.deleteCourseEvent(courseId, id)
        setEvents((p) => p.filter((e) => e.id !== id))
        toast({ title: t("teacherEditor.toast.eventDeleted"), variant: "success" })
      } catch {
        toast({ title: t("teacherEditor.toast.eventDeleteFailed"), variant: "destructive" })
      }
    },
    [courseId, confirm, t],
  )

  return {
    events,
    form,
    setForm,
    editingId,
    saving,
    startEdit,
    save,
    remove,
    resetForm,
  }
}
