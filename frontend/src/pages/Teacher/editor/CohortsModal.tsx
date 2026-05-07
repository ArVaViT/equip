import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { CheckCircle, Pencil, Save, Trash2 } from "lucide-react"
import { Modal } from "@/components/patterns"
import { CohortStatusBadge } from "./badges"
import type { CohortFormState } from "./types"
import type { Cohort } from "@/types"
import { formatDate } from "@/i18n/format"

interface Props {
  open: boolean
  onClose: () => void
  cohorts: Cohort[]
  form: CohortFormState
  onFormChange: (next: CohortFormState) => void
  editingId: string | null
  saving: boolean
  onSave: () => void
  onCancelEdit: () => void
  onEdit: (c: Cohort) => void
  onDelete: (id: string) => void
  onComplete: (id: string) => void
}

export function CohortsModal({
  open,
  onClose,
  cohorts,
  form,
  onFormChange,
  editingId,
  saving,
  onSave,
  onCancelEdit,
  onEdit,
  onDelete,
  onComplete,
}: Props) {
  const patch = (p: Partial<CohortFormState>) => onFormChange({ ...form, ...p })
  const canSubmit = form.name.trim() && form.start_date && form.end_date && !saving

  return (
    <Modal open={open} onClose={onClose} title="Manage Cohorts">
      <div className="space-y-4">
        <div className="space-y-3 border rounded-lg p-3 bg-muted/30">
          <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
            {editingId ? "Edit Cohort" : "Create Cohort"}
          </p>
          <Input
            value={form.name}
            onChange={(e) => patch({ name: e.target.value })}
            placeholder="Cohort name (e.g. Spring 2026)"
          />
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <Label className="text-xs">Start Date</Label>
              <Input
                type="date"
                value={form.start_date}
                onChange={(e) => patch({ start_date: e.target.value })}
                className="text-sm"
              />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">End Date</Label>
              <Input
                type="date"
                value={form.end_date}
                onChange={(e) => patch({ end_date: e.target.value })}
                className="text-sm"
              />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <Label className="text-xs">Enrollment Start</Label>
              <Input
                type="datetime-local"
                value={form.enrollment_start}
                onChange={(e) => patch({ enrollment_start: e.target.value })}
                className="text-sm"
              />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Enrollment End</Label>
              <Input
                type="datetime-local"
                value={form.enrollment_end}
                onChange={(e) => patch({ enrollment_end: e.target.value })}
                className="text-sm"
              />
            </div>
          </div>
          <div className="space-y-1">
            <Label className="text-xs">Max Students (optional)</Label>
            <Input
              type="number"
              value={form.max_students}
              onChange={(e) => patch({ max_students: e.target.value })}
              placeholder="Unlimited"
              className="text-sm"
            />
          </div>
          <div className="flex gap-2">
            <Button size="sm" onClick={onSave} disabled={!canSubmit}>
              <Save className="h-3.5 w-3.5 mr-1.5" />
              {saving ? "Saving…" : editingId ? "Update Cohort" : "Create Cohort"}
            </Button>
            {editingId && (
              <Button size="sm" variant="ghost" onClick={onCancelEdit}>
                Cancel
              </Button>
            )}
          </div>
        </div>

        {cohorts.length === 0 ? (
          <p className="text-sm text-muted-foreground text-center py-4">No cohorts yet.</p>
        ) : (
          <div className="space-y-2 max-h-72 overflow-y-auto">
            {cohorts.map((c) => (
              <CohortRow
                key={c.id}
                cohort={c}
                onEdit={onEdit}
                onDelete={onDelete}
                onComplete={onComplete}
              />
            ))}
          </div>
        )}
      </div>
    </Modal>
  )
}

interface RowProps {
  cohort: Cohort
  onEdit: (c: Cohort) => void
  onDelete: (id: string) => void
  onComplete: (id: string) => void
}

function CohortRow({ cohort, onEdit, onDelete, onComplete }: RowProps) {
  return (
    <div className="flex items-start gap-3 p-3 border rounded-lg">
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-1">
          <p className="text-sm font-medium truncate">{cohort.name}</p>
          <CohortStatusBadge status={cohort.status} />
        </div>
        <p className="text-xs text-muted-foreground">
          {formatDate(cohort.start_date)} &mdash;{" "}
          {formatDate(cohort.end_date)}
        </p>
        <p className="text-xs text-muted-foreground mt-0.5">
          {cohort.student_count} student{cohort.student_count !== 1 ? "s" : ""}
          {cohort.max_students && ` / ${cohort.max_students} max`}
        </p>
        {cohort.enrollment_start && cohort.enrollment_end && (
          <p className="text-[10px] text-muted-foreground/70 mt-0.5">
            Enrollment: {formatDate(cohort.enrollment_start)} —{" "}
            {formatDate(cohort.enrollment_end)}
          </p>
        )}
      </div>
      <div className="flex flex-col gap-1 shrink-0">
        <Button variant="ghost" size="sm" className="h-7 text-xs" onClick={() => onEdit(cohort)}>
          <Pencil className="h-3 w-3" />
        </Button>
        {cohort.status === "active" && (
          <Button
            variant="ghost"
            size="sm"
            className="h-7 text-xs text-success hover:text-success"
            onClick={() => onComplete(cohort.id)}
          >
            <CheckCircle className="h-3 w-3" />
          </Button>
        )}
        <Button
          variant="ghost"
          size="sm"
          className="h-7 text-xs text-destructive hover:text-destructive"
          onClick={() => onDelete(cohort.id)}
        >
          <Trash2 className="h-3 w-3" />
        </Button>
      </div>
    </div>
  )
}
