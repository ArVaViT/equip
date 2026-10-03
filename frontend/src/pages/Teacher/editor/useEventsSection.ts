import { useCallback, useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { coursesService } from "@/services/courses"
import { getErrorDetail } from "@/lib/errorDetail"
import { toast } from "@/lib/toast"
import { isoToLocalInput, localInputToIso } from "@/i18n/format"
import { getDisplayTimeZone } from "@/i18n/timeZone"
import { seriesLastDay } from "@/lib/eventTime"
import type { CourseEventPayload, SeriesScope } from "@/services/calendar"
import type { CourseEvent } from "@/types"
import type { useConfirm } from "@/components/ui/alert-dialog"
import { EMPTY_EVENT_FORM, MAX_SERIES, takesTime, type EventFormState } from "./types"

type Confirm = ReturnType<typeof useConfirm>

/** The server lists events by date; keep that order after a local insert
 *  or a moved date, so a new event lands where it belongs in the list
 *  instead of at the bottom until the next reload. */
function byDate(events: CourseEvent[]): CourseEvent[] {
  return [...events].sort((a, b) => a.event_date.localeCompare(b.event_date))
}

/** A save or a delete waiting for "which lessons of the series?". */
export interface PendingScope {
  action: "save" | "delete"
  eventId: string
}

interface EventsSection {
  events: CourseEvent[]
  form: EventFormState
  setForm: (v: EventFormState) => void
  editingId: string | null
  /** The event being edited, when it belongs to a weekly series. */
  editingSeries: boolean
  saving: boolean
  startEdit: (ev: CourseEvent) => void
  save: () => Promise<void>
  remove: (id: string) => Promise<void>
  resetForm: () => void
  pendingScope: PendingScope | null
  chooseScope: (scope: SeriesScope) => void
  cancelScope: () => void
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
  const [pendingScope, setPendingScope] = useState<PendingScope | null>(null)

  const reload = useCallback(async (): Promise<CourseEvent[] | null> => {
    if (!courseId) return null
    try {
      const fresh = await coursesService.getCourseEventsForEdit(courseId)
      setEvents(fresh)
      return fresh
    } catch {
      // The list stays as it was; the save itself already succeeded.
      return null
    }
  }, [courseId])

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
      recording_url: ev.recording_url ?? "",
      duration_minutes: ev.duration_minutes ? String(ev.duration_minutes) : "",
      repeat_every: "0",
      repeat_count: EMPTY_EVENT_FORM.repeat_count,
    })
    setEditingId(ev.id)
  }, [])

  const editingSeries = Boolean(editingId && events.find((e) => e.id === editingId)?.series_id)

  const submit = useCallback(
    async (scope: SeriesScope) => {
      if (!courseId || !form.title.trim() || !form.event_date) return
      setSaving(true)
      const isoDate = localInputToIso(form.event_date)
      if (!isoDate) {
        setSaving(false)
        return
      }
      const timeZone = getDisplayTimeZone()
      const payload: CourseEventPayload = {
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
        // `null` for the same reason: clearing the field clears the link.
        recording_url: form.recording_url.trim() || null,
        // A deadline has no length, whatever the select last held.
        duration_minutes:
          takesTime(form.event_type) && form.duration_minutes ? Number(form.duration_minutes) : null,
      }
      // Hidden controls keep their values: a teacher who picked "every
      // week" and then turned the class into a deadline must not get
      // eight deadlines.
      const every = takesTime(form.event_type) ? Number(form.repeat_every) : 0
      const count = Math.min(MAX_SERIES, Math.max(1, Number(form.repeat_count) || 1))
      const lastDay = every > 0 && count > 1 ? seriesLastDay(form.event_date, every, count) : null
      try {
        if (editingId) {
          const updated = await coursesService.updateCourseEvent(
            courseId,
            editingId,
            { ...payload, time_zone: timeZone },
            scope,
          )
          if (scope === "this") {
            setEvents((p) => byDate(p.map((ev) => (ev.id === editingId ? updated : ev))))
          } else {
            await reload()
          }
          toast({ title: t("teacherEditor.toast.eventUpdated"), variant: "success" })
        } else if (lastDay) {
          await coursesService.createCourseEvent(courseId, {
            ...(payload as CourseEventPayload & { title: string; event_date: string }),
            repeat: { every_weeks: every, until: lastDay, time_zone: timeZone },
          })
          await reload()
          toast({ title: t("eventSeries.created", { count }), variant: "success" })
        } else {
          const created = await coursesService.createCourseEvent(
            courseId,
            payload as CourseEventPayload & { title: string; event_date: string },
          )
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
    },
    [courseId, form, editingId, resetForm, reload, t],
  )

  const save = useCallback(async () => {
    if (editingId && editingSeries) {
      setPendingScope({ action: "save", eventId: editingId })
      return
    }
    await submit("this")
  }, [editingId, editingSeries, submit])

  const destroy = useCallback(
    async (id: string, scope: SeriesScope) => {
      if (!courseId) return
      try {
        await coursesService.deleteCourseEvent(courseId, id, scope)
        let remaining: CourseEvent[] | null
        if (scope === "this") {
          setEvents((p) => p.filter((e) => e.id !== id))
          remaining = null
        } else {
          remaining = await reload()
        }
        // The lesson open in the form may have gone with the series —
        // saving it then would answer 404.
        const editedGone = editingId === id || (remaining !== null && !remaining.some((e) => e.id === editingId))
        if (editingId && editedGone) resetForm()
        toast({ title: t("teacherEditor.toast.eventDeleted"), variant: "success" })
      } catch {
        toast({ title: t("teacherEditor.toast.eventDeleteFailed"), variant: "destructive" })
      }
    },
    [courseId, editingId, reload, resetForm, t],
  )

  const remove = useCallback(
    async (id: string) => {
      if (!courseId) return
      if (events.find((e) => e.id === id)?.series_id) {
        // The scope dialog is the confirmation: it names what goes.
        setPendingScope({ action: "delete", eventId: id })
        return
      }
      const ok = await confirm({
        title: t("teacherEditor.confirm.deleteEventTitle"),
        confirmLabel: t("teacherEditor.confirm.deleteEventAction"),
        tone: "destructive",
      })
      if (!ok) return
      await destroy(id, "this")
    },
    [courseId, events, confirm, destroy, t],
  )

  const chooseScope = useCallback(
    (scope: SeriesScope) => {
      const pending = pendingScope
      setPendingScope(null)
      if (!pending) return
      if (pending.action === "save") void submit(scope)
      else void destroy(pending.eventId, scope)
    },
    [pendingScope, submit, destroy],
  )

  const cancelScope = useCallback(() => setPendingScope(null), [])

  return {
    events,
    form,
    setForm,
    editingId,
    editingSeries,
    saving,
    startEdit,
    save,
    remove,
    resetForm,
    pendingScope,
    chooseScope,
    cancelScope,
  }
}
