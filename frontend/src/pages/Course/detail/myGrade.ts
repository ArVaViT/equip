import type { MyCourseGrade, MyGradeItem } from "@/types"

export interface MyGradeDisplay {
  /** The headline — «текущая», or the hand-set grade when there is one. */
  headline: string | null
  /** True when a teacher set it by hand, so the card can say so. */
  isManual: boolean
  /** «Итоговая», only once it differs. `null` = nothing to add. */
  finalText: string | null
  /** i18n key explaining an absent number. `null` when there is one. */
  noteKey: string | null
}

const NOTE_BY_STATE: Record<string, string> = {
  completion_pass: "myGrade.state.byCompletion",
  not_graded_yet: "myGrade.state.notGradedYet",
  zero_weighted: "myGrade.state.notWeighted",
  not_assessed: "myGrade.state.notAssessed",
}

/** Percent with one decimal, matching every teacher surface exactly. */
function formatScore(score: number, symbol: string | null): string {
  return symbol ? `${score.toFixed(1)}% ${symbol}` : `${score.toFixed(1)}%`
}

/**
 * What a student is told about their own grade.
 *
 * The same rules as the teacher's screens, in the same order, because the two
 * of them have to be able to talk about it:
 *
 * 1. a hand-set grade wins — it IS the official grade (D7);
 * 2. no number means say why, never a bare dash and never a zero;
 * 3. otherwise «текущая», with «итоговая» underneath once they diverge.
 *
 * `scores_withheld` is the fourth case and the quiet one: a pass/fail course is
 * decided by whether every required piece of work was accepted, not by an
 * average (D2), so its weighted percentage is not the result. Showing it would
 * be the hidden-average behaviour the design set out to remove.
 */
export function myGradeDisplay(grade: MyCourseGrade): MyGradeDisplay {
  if (grade.official_grade) {
    return { headline: grade.official_grade, isManual: true, finalText: null, noteKey: null }
  }
  if (grade.scores_withheld) {
    return { headline: null, isManual: false, finalText: null, noteKey: "myGrade.state.byCompletion" }
  }
  if (grade.current_score === null || grade.final_score === null) {
    return {
      headline: null,
      isManual: false,
      finalText: null,
      noteKey: NOTE_BY_STATE[grade.result_state] ?? null,
    }
  }
  return {
    headline: formatScore(grade.current_score, grade.current_symbol),
    isManual: false,
    finalText: grade.scores_differ ? formatScore(grade.final_score, grade.final_symbol) : null,
    noteKey: null,
  }
}

/** Items a student still owes, in the order they should worry about them. */
export function outstandingItems(items: MyGradeItem[]): MyGradeItem[] {
  const order: Record<MyGradeItem["status"], number> = {
    not_submitted: 0,
    pending_review: 1,
    graded: 2,
    excused: 3,
  }
  return [...items].sort((a, b) => order[a.status] - order[b.status] || a.title.localeCompare(b.title))
}
