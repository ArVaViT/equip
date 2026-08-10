import { formatGradePercent } from "./formatGrade"

export interface GradePair {
  /** «Текущая» — over the work that has been marked. What to lead with. */
  current: string
  /** «Итоговая» — outstanding work counted as zero. */
  final: string
  /** True when the two differ, so the surface renders the one-line reason. */
  differ: boolean
}

/** The one sentence that explains the gap, in the same words everywhere. */
export const PAIR_EXPLAINER_KEY = "gradebook.pair.explainer"

/**
 * The two grades a student has at any moment, formatted as a pair.
 *
 * They answer different questions and both are true: «текущая» is how the
 * marked work is going, «итоговая» is what the course is worth if nothing more
 * is handed in. In week two those are 100% and 25%.
 *
 * The design's rule (D10) is that nobody gets one and not the other. Showing
 * the student «текущая» while the teacher reads «итоговая» produces a
 * conversation where each side is certain their own number is the grade and
 * neither can explain the other's — and the student meets the harsher number
 * for the first time when a certificate is refused.
 *
 * When the two are equal there is one number and nothing to explain, so the
 * caller renders `current` alone and drops the line.
 */
export function gradePair(
  currentScore: number,
  finalScore: number,
  currentSymbol: string | null,
  finalSymbol: string | null,
): GradePair {
  const withSymbol = (score: number, symbol: string | null) =>
    symbol ? `${formatGradePercent(score)} ${symbol}` : formatGradePercent(score)

  return {
    current: withSymbol(currentScore, currentSymbol),
    final: withSymbol(finalScore, finalSymbol),
    // Compared on the numbers, not the formatted strings: two scores that round
    // to the same text need no explanation, and a difference in the third
    // decimal is not a thing to say out loud to anyone.
    differ: currentScore !== finalScore,
  }
}
