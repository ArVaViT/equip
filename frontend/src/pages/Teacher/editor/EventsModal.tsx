import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { Pencil, Save, Trash2 } from "lucide-react"
import { Modal } from "@/components/patterns"
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

const EVENT_TYPES: readonly { value: string; label: string }[] = [
  { value: "deadline", label: "Deadline" },
  { value: "live_session", label: "Live Session" },
  { value: "exam", label: "Exam" },
  { value: "other", label: "Other" },
]

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
  const patch = (p: Partial<EventFormState>) => onFormChange({ ...form, ...p })
  const canSubmit = form.title.trim() && form.event_date && !saving

  return (
    <Modal open={open} onClose={onClose} title="Course Events">
      <div className="space-y-4">
        <div className="space-y-3 border rounded-lg p-3 bg-muted/30">
          <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
            {editingId ? "Edit Event" : "Create Event"}
          </p>
          <Input
            value={form.title}
            onChange={(e) => patch({ title: e.target.value })}
            placeholder="Event title"
          />
          <Textarea
            fieldSize="sm"
            value={form.description}
            onChange={(e) => patch({ description: e.target.value })}
            placeholder="Description (optional)"
          />
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <Label className="text-xs">Type</Label>
              <select
                value={form.event_type}
                onChange={(e) => patch({ event_type: e.target.value })}
                className="w-full text-sm border rounded-md px-2 py-1.5 bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
              >
                {EVENT_TYPES.map((t) => (
                  <option key={t.value} value={t.value}>
                    {t.label}
                  </option>
                ))}
              </select>
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Date & Time</Label>
              <Input
                type="datetime-local"
                value={form.event_date}
                onChange={(e) => patch({ event_date: e.target.value })}
                className="text-sm"
              />
            </div>
          </div>
          <div className="flex gap-2">
            <Button size="sm" onClick={onSave} disabled={!canSubmit}>
              <Save className="h-3.5 w-3.5 mr-1.5" />
              {saving ? "Saving…" : editingId ? "Update Event" : "Create Event"}
            </Button>
            {editingId && (
              <Button size="sm" variant="ghost" onClick={onCancelEdit}>
                Cancel
              </Button>
            )}
          </div>
        </div>

        {events.length === 0 ? (
          <p className="text-sm text-muted-foreground text-center py-4">No events yet.</p>
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
        <Button variant="ghost" size="sm" className="h-7 text-xs" onClick={() => onEdit(event)}>
          <Pencil className="h-3 w-3" />
        </Button>
        <Button
          variant="ghost"
          size="sm"
          className="h-7 text-xs text-destructive hover:text-destructive"
          onClick={() => onDelete(event.id)}
        >
          <Trash2 className="h-3 w-3" />
        </Button>
      </div>
    </div>
  )
}
