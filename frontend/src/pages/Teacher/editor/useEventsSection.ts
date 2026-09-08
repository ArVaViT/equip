import { useCallback, useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { coursesService } from "@/services/courses"
import { getErrorDetail } from "@/lib/errorDetail"
import { toast } from "@/lib/toast"
import { isoToLocalInput, localInputToIso } from "@/i18n/format"
import type { CourseEvent } from "@/types"
import type { useConfirm } from "@/components/ui/alert-dialog"
import { EMPTY_EVENT_FORM, type EventFormState } from "./types"

type Confirm = ReturnType<typeof useConfirm>

/** The server lists events by date; keep that order after a local insert
 *  or a moved date, so a new event lands where it belongs in the list
 *  instead of at the bottom until the next reload. */
function byDate(events: CourseEvent[]): CourseEvent[] {
  return [...events].sort((a, b) => a.event_date.localeCompare(b.event_date))
}

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
      .getCourseEventsForEdit(courseId)
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
      event_date: isoToLocalInput(ev.event_date),
      meeting_url: ev.meeting_url ?? "",
    })
    setEditingId(ev.id)
  }, [])

  const save = useCallback(async () => {
    if (!courseId || !form.title.trim() || !form.event_date) return
    setSaving(true)
    const isoDate = localInputToIso(form.event_date)
    if (!isoDate) {
      setSaving(false)
      return
    }
    const payload = {
      title: form.title.trim(),
      description: form.description.trim() || undefined,
      event_type: form.event_type,
      event_date: isoDate,
      // `null`, not `undefined`, when the field is empty: on an update
      // this is how a teacher takes a link back off an event. Sent
      // `undefined` it would be dropped from the JSON body, the server
      // would see an absent key, and `exclude_unset` would leave the old
      // link in place — the field would look cleared and would not be.
      meeting_url: form.meeting_url.trim() || null,
    }
    try {
      if (editingId) {
        const updated = await coursesService.updateCourseEvent(courseId, editingId, payload)
        setEvents((p) => byDate(p.map((ev) => (ev.id === editingId ? updated : ev))))
        toast({ title: t("teacherEditor.toast.eventUpdated"), variant: "success" })
      } else {
        const created = await coursesService.createCourseEvent(courseId, payload)
        setEvents((p) => byDate([...p, created]))
        toast({ title: t("teacherEditor.toast.eventCreated"), variant: "success" })
      }
      resetForm()
    } catch (err) {
      // Was a fixed "could not save the event", which is true and
      // useless: the commonest way to fail here is now a meeting link
      // the server refused, and the server says exactly what is wrong
      // with it. `getErrorDetail` renders that 422 in the reader's
      // language and falls back to the old sentence for everything else.
      toast({
        title: getErrorDetail(err, t("teacherEditor.toast.eventSaveFailed")),
        variant: "destructive",
      })
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
