import type { Assignment } from "@/types"
import { isoToLocalInput, localInputToIso } from "@/i18n/format"

export interface AssignmentFormState {
  title: string
  description: string
  maxScore: number
  /** ``YYYY-MM-DDTHH:MM`` in the teacher's zone; ``""`` for no deadline. */
  dueDate: string
}

export const EMPTY_ASSIGNMENT_FORM: AssignmentFormState = {
  title: "",
  description: "",
  maxScore: 100,
  dueDate: "",
}

export function assignmentToFormState(a: Assignment): AssignmentFormState {
  return {
    title: a.title,
    description: a.description ?? "",
    maxScore: a.max_score,
    // The stored instant, shown on the teacher's clock. ``slice(0, 10)``
    // took the UTC date, and a deadline saved as a bare date became UTC
    // midnight — the evening before, in Indiana.
    dueDate: isoToLocalInput(a.due_date),
  }
}

/**
 * Converts the UI form into the `create`/`update` payload shape. Empty
 * strings become null so the backend clears the column.
 */
export function formStateToPayload(form: AssignmentFormState) {
  return {
    title: form.title.trim(),
    description: form.description.trim() || null,
    max_score: form.maxScore,
    due_date: localInputToIso(form.dueDate),
  }
}
