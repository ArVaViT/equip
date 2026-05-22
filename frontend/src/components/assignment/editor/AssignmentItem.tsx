import { useState } from "react"
import { useTranslation } from "react-i18next"
import { Card } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { ChevronDown, ChevronRight, Loader2, Pencil, Trash2 } from "lucide-react"
import { coursesService } from "@/services/courses"
import { toast } from "@/lib/toast"
import type { Assignment, AssignmentSubmission } from "@/types"
import { AssignmentForm } from "./AssignmentForm"
import { SubmissionGrader } from "./SubmissionGrader"
import {
  assignmentToFormState,
  formStateToPayload,
  type AssignmentFormState,
} from "./types"
import { formatDate } from "@/i18n/format"

interface Props {
  assignment: Assignment
  onDelete: (id: string) => void
  onUpdate: (updated: Assignment) => void
}

/**
 * Expandable row that shows an assignment, inline edit form, and its
 * list of student submissions (lazy-loaded on first expand).
 */
export function AssignmentItem({ assignment, onDelete, onUpdate }: Props) {
  const { t } = useTranslation()
  const [expanded, setExpanded] = useState(false)
  const [submissions, setSubmissions] = useState<AssignmentSubmission[]>([])
  const [loadingSubs, setLoadingSubs] = useState(false)
  const [editing, setEditing] = useState(false)
  const [form, setForm] = useState<AssignmentFormState>(() =>
    assignmentToFormState(assignment),
  )
  const [updating, setUpdating] = useState(false)

  const toggleExpand = async () => {
    if (!expanded) {
      setLoadingSubs(true)
      try {
        setSubmissions(await coursesService.getSubmissions(assignment.id))
      } catch {
        setSubmissions([])
      } finally {
        setLoadingSubs(false)
      }
    }
    setExpanded((v) => !v)
  }

  const startEdit = () => {
    setForm(assignmentToFormState(assignment))
    setEditing(true)
  }

  const handleUpdate = async () => {
    if (!form.title.trim()) {
      toast({ title: t("assignmentEditor.validation.titleRequired"), variant: "destructive" })
      return
    }
    setUpdating(true)
    try {
      const updated = await coursesService.updateAssignment(
        assignment.id,
        formStateToPayload(form),
      )
      onUpdate(updated)
      setEditing(false)
      toast({ title: t("assignmentEditor.toast.updated"), variant: "success" })
    } catch {
      toast({ title: t("assignmentEditor.toast.updateFailed"), variant: "destructive" })
    } finally {
      setUpdating(false)
    }
  }

  return (
    <Card>
      <div
        role="button"
        tabIndex={0}
        className="flex items-center gap-2 p-3 cursor-pointer select-none"
        onClick={toggleExpand}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault()
            void toggleExpand()
          }
        }}
      >
        {expanded ? (
          <ChevronDown className="h-4 w-4 text-muted-foreground shrink-0" strokeWidth={1.75} />
        ) : (
          <ChevronRight className="h-4 w-4 text-muted-foreground shrink-0" strokeWidth={1.75} />
        )}
        <div className="flex-1 min-w-0">
          <span className="text-sm font-medium">{assignment.title}</span>
          <div className="flex items-center gap-3 text-xs text-muted-foreground">
            <span>{t("assignmentEditor.item.maxPts", { max: assignment.max_score })}</span>
            {assignment.due_date && (
              <span>
                {t("assignmentEditor.item.due", { date: formatDate(assignment.due_date) })}
              </span>
            )}
          </div>
        </div>
        <Button
          variant="ghost"
          size="sm"
          className="h-7 w-7 p-0 shrink-0"
          onClick={(e) => {
            e.stopPropagation()
            startEdit()
          }}
          aria-label={t("assignmentEditor.item.editAria", { title: assignment.title })}
        >
          <Pencil className="h-3.5 w-3.5" strokeWidth={1.75} />
        </Button>
        <Button
          variant="ghost"
          size="sm"
          className="text-destructive hover:text-destructive h-7 w-7 p-0 shrink-0"
          onClick={(e) => {
            e.stopPropagation()
            onDelete(assignment.id)
          }}
          aria-label={t("assignmentEditor.item.deleteAria", { title: assignment.title })}
        >
          <Trash2 className="h-3.5 w-3.5" strokeWidth={1.75} />
        </Button>
      </div>

      {editing && (
        <div className="border-t px-4 py-3">
          <AssignmentForm
            value={form}
            onChange={setForm}
            onSubmit={handleUpdate}
            onCancel={() => setEditing(false)}
            submitting={updating}
            mode="edit"
          />
        </div>
      )}

      {expanded && (
        <div className="border-t px-4 pb-4">
          {assignment.description && (
            <p className="text-xs text-muted-foreground py-2">{assignment.description}</p>
          )}

          {loadingSubs ? (
            <div className="flex items-center justify-center py-6">
              <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" strokeWidth={1.75} />
            </div>
          ) : submissions.length === 0 ? (
            <p className="text-sm text-muted-foreground py-4 text-center">
              {t("assignmentEditor.item.noSubmissions")}
            </p>
          ) : (
            <div className="space-y-3 mt-3">
              <h4 className="text-xs font-semibold text-muted-foreground">
                {t("assignmentEditor.item.submissionsCount", { count: submissions.length })}
              </h4>
              {submissions.map((sub) => (
                <SubmissionGrader
                  key={sub.id}
                  submission={sub}
                  maxScore={assignment.max_score}
                  onUpdate={(updated) => {
                    setSubmissions((prev) =>
                      prev.map((s) => (s.id === updated.id ? updated : s)),
                    )
                  }}
                />
              ))}
            </div>
          )}
        </div>
      )}
    </Card>
  )
}
