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
import { CalendarDays, Pencil, Save, Trash2 } from "lucide-react"
import { EmptyState, Modal } from "@/components/patterns"
import { EventTypeBadge } from "./badges"
import type { EventFormState } from "./types"
import type { CourseEvent } from "@/types"
import { formatDateTime } from "@/i18n/format"

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
}

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
}: Props) {
  const { t } = useTranslation()
  const patch = (p: Partial<EventFormState>) => onFormChange({ ...form, ...p })
  const canSubmit = form.title.trim() && form.event_date && !saving

  return (
    <Modal open={open} onClose={onClose} title={t("teacherEditor.modals.events.title")}>
      <div className="space-y-4">
        <div className="space-y-3 rounded-md border bg-muted/30 p-3">
          <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
            {editingId
              ? t("teacherEditor.modals.events.editEvent")
              : t("teacherEditor.modals.events.createEvent")}
          </p>
          <Input
            value={form.title}
            onChange={(e) => patch({ title: e.target.value })}
            placeholder={t("teacherEditor.modals.events.titlePlaceholder")}
          />
          <Textarea
            fieldSize="sm"
            value={form.description}
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
                      {t(`teacherEditor.modals.events.types.${value}`)}
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
        <p className="text-xs text-muted-foreground">
          {formatDateTime(event.event_date)}
        </p>
        {event.description && (
          <p className="text-xs text-muted-foreground/70 mt-0.5 line-clamp-1">
            {event.description}
          </p>
        )}
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
