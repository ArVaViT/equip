import { useTranslation } from "react-i18next"
import { Button } from "@/components/ui/button"
import { DateTimePicker } from "@/components/ui/datetime-picker"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Textarea } from "@/components/ui/textarea"
import { CalendarDays, Pencil, Repeat, Save, Trash2 } from "lucide-react"
import { EmptyState, Modal } from "@/components/patterns"
import { EventTypeBadge } from "./badges"
import { DURATION_CHOICES, MAX_SERIES, takesTime, type EventFormState } from "./types"
import type { PendingScope } from "./useEventsSection"
import type { CourseEvent } from "@/types"
import type { SeriesScope } from "@/services/calendar"
import { SeriesScopeDialog } from "@/components/calendar/SeriesScopeDialog"
import { formatDurationMinutes, formatEventTimeRange } from "@/components/calendar/eventTimeFormat"
import { seriesLastDay } from "@/lib/eventTime"
import { JoinMeetingLink } from "@/components/calendar/JoinMeetingLink"
import { RecordingLink } from "@/components/calendar/RecordingLink"
import { isAbsoluteHttpUrl } from "@/lib/url"
import { formatDateLong, formatDateTime } from "@/i18n/format"
import { useId } from "react"

/** Mirrors ``CourseEventCreate`` on the server (``max_length``). */
const TITLE_MAX = 255
const DESCRIPTION_MAX = 5000
/** Mirrors ``MEETING_URL_MAX_LENGTH`` in ``app/core/meeting_url.py``. */
const MEETING_URL_MAX = 2048

interface Props {
  open: boolean
  onClose: () => void
  events: CourseEvent[]
  form: EventFormState
  onFormChange: (next: EventFormState) => void
  editingId: string | null
  saving: boolean
  onSave: () => void
  onCancelEdit: () => void
  onEdit: (e: CourseEvent) => void
  onDelete: (id: string) => void
  pendingScope?: PendingScope | null
  onChooseScope?: (scope: SeriesScope) => void
  onCancelScope?: () => void
}

import { EVENT_TYPE_LABEL_KEYS } from "./eventTypes"

const EVENT_TYPE_VALUES = ["deadline", "live_session", "exam", "other"] as const

export function EventsModal({
  open,
  onClose,
  events,
  form,
  onFormChange,
  editingId,
  saving,
  onSave,
  onCancelEdit,
  onEdit,
  onDelete,
  pendingScope = null,
  onChooseScope,
  onCancelScope,
}: Props) {
  const { t, i18n } = useTranslation()
  const ids = useId()
  const patch = (p: Partial<EventFormState>) => onFormChange({ ...form, ...p })
  // Blank is fine — most events have no meeting. Only a link that has
  // been typed and is not a link is an error, and it blocks the save so
  // the teacher is not told about it by a toast after the fact.
  const meetingUrlTyped = form.meeting_url.trim()
  const meetingUrlBroken = meetingUrlTyped !== "" && !isAbsoluteHttpUrl(meetingUrlTyped)
  const recordingTyped = form.recording_url.trim()
  const recordingBroken = recordingTyped !== "" && !isAbsoluteHttpUrl(recordingTyped)
  const repeating = !editingId && takesTime(form.event_type) && form.repeat_every !== "0"
  const count = Number(form.repeat_count)
  const countBroken = repeating && !(Number.isInteger(count) && count >= 2 && count <= MAX_SERIES)
  const lastDay = repeating && !countBroken ? seriesLastDay(form.event_date, Number(form.repeat_every), count) : null
  const seriesHint = countBroken
    ? t("eventSeries.countRange", { max: MAX_SERIES })
    : lastDay
      ? t("eventSeries.lastOn", {
          date: formatDateLong(`${lastDay}T12:00:00Z`, { timeZone: "UTC" }),
        })
      : ""
  const canSubmit =
    form.title.trim() && form.event_date && !meetingUrlBroken && !recordingBroken && !countBroken && !saving

  return (
    <Modal open={open} onClose={onClose} title={t("teacherEditor.modals.events.title")}>
      <div className="space-y-4">
        <div className="space-y-3 rounded-md border bg-muted/30 p-3">
          <p className="text-xs font-medium text-ink-muted uppercase tracking-wide">
            {editingId
              ? t("teacherEditor.modals.events.editEvent")
              : t("teacherEditor.modals.events.createEvent")}
          </p>
          <Input
            value={form.title}
            maxLength={TITLE_MAX}
            onChange={(e) => patch({ title: e.target.value })}
            placeholder={t("teacherEditor.modals.events.titlePlaceholder")}
          />
          <Textarea
            fieldSize="sm"
            value={form.description}
            maxLength={DESCRIPTION_MAX}
            onChange={(e) => patch({ description: e.target.value })}
            placeholder={t("teacherEditor.modals.events.descriptionPlaceholder")}
          />
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <Label className="text-xs">{t("teacherEditor.modals.events.type")}</Label>
              <Select
                value={form.event_type}
                onValueChange={(v) => patch({ event_type: v })}
              >
                <SelectTrigger size="sm">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {EVENT_TYPE_VALUES.map((value) => (
                    <SelectItem key={value} value={value}>
                      {t(EVENT_TYPE_LABEL_KEYS[value])}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label className="text-xs">{t("teacherEditor.modals.events.dateTime")}</Label>
              <DateTimePicker
                value={form.event_date}
                onChange={(next) => patch({ event_date: next })}
                className="w-full"
              />
            </div>
          </div>
          {takesTime(form.event_type) && (
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label className="text-xs" htmlFor={`${ids}-duration`}>
                  {t("eventSeries.duration")}
                </Label>
                <Select
                  value={form.duration_minutes || "none"}
                  onValueChange={(v) => patch({ duration_minutes: v === "none" ? "" : v })}
                >
                  <SelectTrigger size="sm" id={`${ids}-duration`}>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="none">{t("eventSeries.durationNone")}</SelectItem>
                    {DURATION_CHOICES.map((m) => (
                      <SelectItem key={m} value={String(m)}>
                        {formatDurationMinutes(m, i18n.language)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              {/* A series is made once, when the event is created; after
                  that each lesson is its own row, edited one or many at
                  a time through the scope question. */}
              {!editingId && (
                <div className="space-y-1">
                  <Label className="text-xs" htmlFor={`${ids}-repeat`}>
                    {t("eventSeries.repeat")}
                  </Label>
                  <Select
                    value={form.repeat_every}
                    onValueChange={(v) => patch({ repeat_every: v as EventFormState["repeat_every"] })}
                  >
                    <SelectTrigger size="sm" id={`${ids}-repeat`}>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="0">{t("eventSeries.repeatNone")}</SelectItem>
                      <SelectItem value="1">{t("eventSeries.repeatWeekly")}</SelectItem>
                      <SelectItem value="2">{t("eventSeries.repeatBiweekly")}</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              )}
            </div>
          )}
          {!editingId && takesTime(form.event_type) && form.repeat_every !== "0" && (
            <div className="space-y-1">
              <Label className="text-xs" htmlFor={`${ids}-count`}>
                {t("eventSeries.count")}
              </Label>
              <div className="flex items-center gap-3">
                <Input
                  id={`${ids}-count`}
                  type="number"
                  inputMode="numeric"
                  min={2}
                  max={MAX_SERIES}
                  className="w-24"
                  value={form.repeat_count}
                  onChange={(e) => patch({ repeat_count: e.target.value })}
                  aria-describedby={`${ids}-count-hint`}
                />
                <p id={`${ids}-count-hint`} className="text-xs text-ink-muted">
                  {seriesHint}
                </p>
              </div>
            </div>
          )}
          {/* Optional, and it looks optional: its own labelled row after
              the type and the date, never a required-field asterisk. A
              deadline and an exam in a room have nothing to join, and
              those are most events. */}
          <div className="space-y-1">
            <Label className="text-xs" htmlFor="event-meeting-url">
              {t("meeting.linkLabel")}
            </Label>
            <Input
              id="event-meeting-url"
              type="url"
              inputMode="url"
              value={form.meeting_url}
              maxLength={MEETING_URL_MAX}
              onChange={(e) => patch({ meeting_url: e.target.value })}
              placeholder={t("meeting.linkPlaceholder")}
              aria-invalid={meetingUrlBroken || undefined}
              aria-describedby={
                meetingUrlBroken ? "event-meeting-url-error" : "event-meeting-url-hint"
              }
            />
            {meetingUrlBroken ? (
              // The same sentence the server would answer with, asked
              // for by the same key — so the teacher reads one wording
              // whether the browser caught it or the API did.
              <p id="event-meeting-url-error" role="alert" className="text-xs text-destructive">
                {t("errors.fields.meeting_url")}:{" "}
                {t("errors.validation.meeting_url_not_a_web_address")}
              </p>
            ) : (
              <p id="event-meeting-url-hint" className="text-xs text-ink-muted">
                {t("meeting.linkHint")}
              </p>
            )}
          </div>
          {/* Added after a live session, when there is a recording — so it
              is offered only on a live session being edited (or one that
              already has a link, so it can be taken off). */}
          {editingId && (form.event_type === "live_session" || recordingTyped !== "") && (
            <div className="space-y-1">
              <Label className="text-xs" htmlFor="event-recording-url">
                {t("meeting.recordingLabel")}
              </Label>
              <Input
                id="event-recording-url"
                type="url"
                inputMode="url"
                value={form.recording_url}
                maxLength={MEETING_URL_MAX}
                onChange={(e) => patch({ recording_url: e.target.value })}
                placeholder={t("meeting.recordingPlaceholder")}
                aria-invalid={recordingBroken || undefined}
                aria-describedby={recordingBroken ? "event-recording-url-error" : "event-recording-url-hint"}
              />
              {recordingBroken ? (
                <p id="event-recording-url-error" role="alert" className="text-xs text-destructive">
                  {t("errors.fields.recording_url")}:{" "}
                  {t("errors.validation.meeting_url_not_a_web_address")}
                </p>
              ) : (
                <p id="event-recording-url-hint" className="text-xs text-ink-muted">
                  {t("meeting.recordingHint")}
                </p>
              )}
            </div>
          )}
          <div className="flex gap-2">
            <Button size="sm" onClick={onSave} disabled={!canSubmit}>
              <Save className="h-3.5 w-3.5 mr-1.5" strokeWidth={1.75} />
              {saving
                ? t("teacherEditor.modals.events.saving")
                : editingId
                  ? t("teacherEditor.modals.events.update")
                  : t("teacherEditor.modals.events.create")}
            </Button>
            {editingId && (
              <Button size="sm" variant="ghost" onClick={onCancelEdit}>
                {t("teacherEditor.modals.events.cancel")}
              </Button>
            )}
          </div>
          <p className="text-xs text-ink-muted">{t("teacherEditor.modals.events.notifyHint")}</p>
        </div>

        {events.length === 0 ? (
          <EmptyState
            variant="compact"
            icon={<CalendarDays strokeWidth={1.75} aria-hidden />}
            title={t("teacherEditor.modals.events.empty")}
          />
        ) : (
          <div className="space-y-2 max-h-72 overflow-y-auto">
            {events.map((event) => (
              <EventRow key={event.id} event={event} onEdit={onEdit} onDelete={onDelete} />
            ))}
          </div>
        )}
      </div>
      <SeriesScopeDialog
        open={pendingScope !== null}
        action={pendingScope?.action ?? "save"}
        onChoose={(scope) => onChooseScope?.(scope)}
        onCancel={() => onCancelScope?.()}
      />
    </Modal>
  )
}

function EventRow({
  event,
  onEdit,
  onDelete,
}: {
  event: CourseEvent
  onEdit: (e: CourseEvent) => void
  onDelete: (id: string) => void
}) {
  const { t } = useTranslation()
  return (
    <div className="flex items-start gap-3 p-3 border rounded-lg">
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-0.5">
          <p className="text-sm font-medium truncate">{event.title}</p>
          <EventTypeBadge type={event.event_type} />
        </div>
        {/* «1 октября 2026 г., 18:00» rather than the audit-log
            ``2026-10-01 18:00:00`` — a teacher reading their own
            schedule does not need the seconds; the exact stamp is one
            hover away. */}
        <time
          className="block text-xs text-ink-muted tabular-nums"
          dateTime={event.event_date}
          title={formatDateTime(event.event_date)}
        >
          {formatDateLong(event.event_date, { weekday: "short" })}, {formatEventTimeRange(event)}
          {event.series_id && (
            <span className="ml-1.5 inline-flex items-center gap-0.5 align-middle" title={t("eventSeries.partOfSeries")}>
              <Repeat className="h-3 w-3" strokeWidth={1.75} aria-hidden />
              <span className="sr-only">{t("eventSeries.partOfSeries")}</span>
            </span>
          )}
        </time>
        {event.description && (
          <p className="text-xs text-ink-muted mt-0.5 line-clamp-1">
            {event.description}
          </p>
        )}
        {/* The teacher sees the same button her students will, in the
            same list she edits — which is how she finds out that the
            link she pasted opens the room she meant, before Saturday. */}
        <div className="mt-1.5 flex flex-wrap gap-1.5">
          <JoinMeetingLink url={event.meeting_url} title={event.title} />
          <RecordingLink url={event.recording_url} title={event.title} />
        </div>
      </div>
      <div className="flex flex-col gap-1 shrink-0">
        <Button
          variant="ghost"
          size="sm"
          className="h-7 text-xs"
          onClick={() => onEdit(event)}
          aria-label={t("teacherEditor.modals.events.editAria", { title: event.title })}
        >
          <Pencil className="h-3 w-3" strokeWidth={1.75} />
        </Button>
        <Button
          variant="ghost"
          size="sm"
          className="h-7 text-xs text-destructive hover:text-destructive"
          onClick={() => onDelete(event.id)}
          aria-label={t("teacherEditor.modals.events.deleteAria", { title: event.title })}
        >
          <Trash2 className="h-3 w-3" strokeWidth={1.75} />
        </Button>
      </div>
    </div>
  )
}
