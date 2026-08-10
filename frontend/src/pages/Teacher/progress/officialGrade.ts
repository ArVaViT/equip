import type { StudentProgressEntry } from "@/types"
import { gradePair } from "../gradebook/gradePair"

export interface OfficialGrade {
  /** What to print. Already formatted; `null` means print nothing but the note. */
  text: string | null
  /** «Итоговая», when it differs from what `text` shows. `null` = nothing to add. */
  finalText: string | null
  /** True when a teacher set this by hand, so the UI can mark it as such. */
  isManual: boolean
  /** i18n key explaining an absent number. `null` when there is a number. */
  noteKey: string | null
}

/** Why there is no number, phrased as the fact rather than as an absence. */
const NOTE_BY_STATE: Record<string, string> = {
  completion_pass: "studentProgress.grade.byCompletion",
  not_graded_yet: "studentProgress.grade.notGradedYet",
  zero_weighted: "studentProgress.grade.notWeighted",
  not_assessed: "studentProgress.grade.notAssessed",
}

/**
 * The one grade a teacher should act on, for the progress board.
 *
 * Three rules, in this order, and the order is the whole function:
 *
 * 1. **A hand-set grade wins.** The override *is* the official grade (D7) — it
 *    decides the certificate, the ведомость and the student's own page. A board
 *    showing the computed number next to a teacher's override would be showing
 *    the unofficial one, which is how a student ends up told two things.
 * 2. **No number means say why.** «—» on its own reads as a bug. Each state has
 *    a reason a teacher can act on, and they are different actions: mark the
 *    first submission, set the weights, give this student a grade by hand.
 * 3. Otherwise the weighted percentage, from the same service as the gradebook.
 */
export function officialGrade(entry: StudentProgressEntry): OfficialGrade {
  if (entry.manual_grade) {
    // A hand-set grade replaces both halves of the pair — there is no
    // "current" version of a decision somebody made.
    return { text: entry.manual_grade, finalText: null, isManual: true, noteKey: null }
  }
  if (entry.overall_grade === null || entry.current_grade === null) {
    return {
      text: null,
      finalText: null,
      isManual: false,
      noteKey: NOTE_BY_STATE[entry.result_state] ?? null,
    }
  }

  // Lead with «текущая» — it is the number the student is looking at, so it is
  // the one that makes a conversation between them possible (D10).
  const pair = gradePair(
    entry.current_grade,
    entry.overall_grade,
    entry.current_letter_grade,
    entry.letter_grade,
  )
  return {
    text: pair.current,
    finalText: pair.differ ? pair.final : null,
    isManual: false,
    noteKey: null,
  }

}
