import type { StudentCalculatedGrade } from "@/types"
import { formatGradePercent } from "./formatGrade"

export interface OfficialCell {
  /** The grade to print, already formatted. `null` when there is no number. */
  text: string | null
  /** True when a teacher set it by hand, so the cell can mark it. */
  isManual: boolean
  /** i18n key for the short reason when there is no number. */
  noteKey: string | null
}

const NOTE_BY_STATE: Record<string, string> = {
  completion_pass: "gradebook.table.byCompletion",
  not_graded_yet: "gradebook.table.notGradedYet",
  zero_weighted: "gradebook.table.notWeighted",
  not_assessed: "gradebook.table.notAssessed",
}

const NO_NUMBER = new Set(Object.keys(NOTE_BY_STATE))

/**
 * The Grade Table's last column: the official grade, not a private total.
 *
 * It used to add up raw points across the row, and the sum meant nothing a
 * teacher could act on:
 *
 * - an unattempted quiz contributed **1** to the denominator, whatever it was
 *   really worth, so a 50-point exam nobody had sat cost the same as a
 *   one-point reading;
 * - assignments were counted at `max_score` (usually 100) against quizzes at
 *   10, so one essay silently outweighed every test in the course;
 * - reading and video chapters — which carry no grade at all — each added a
 *   point;
 * - exemptions, the course weights, the institution's bands and the override
 *   were all absent, so this column could disagree with the Summary tab two
 *   clicks away about the same student, and did.
 *
 * The number is now the one the gradebook, the progress board and the CSV all
 * show (D14). What the row is *for* — seeing which cell is empty — is
 * unchanged; that lives in the cells, which is where a teacher was reading it
 * anyway.
 */
export function officialColumn(entry: StudentCalculatedGrade | undefined): OfficialCell {
  if (!entry) return { text: null, isManual: false, noteKey: null }

  // A hand-set grade IS the official grade (D7): it decides the certificate and
  // the ведомость, so the column that claims to be official must show it.
  if (entry.manual_grade) {
    return { text: entry.manual_grade, isManual: true, noteKey: null }
  }

  const { result_state, final_score, letter_grade } = entry.breakdown
  if (NO_NUMBER.has(result_state)) {
    return { text: null, isManual: false, noteKey: NOTE_BY_STATE[result_state] ?? null }
  }
  const percent = formatGradePercent(final_score)
  return {
    text: letter_grade ? `${percent} ${letter_grade}` : percent,
    isManual: false,
    noteKey: null,
  }
}
