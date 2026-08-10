/**
 * The one place a grade percentage becomes text.
 *
 * There were three. The progress board rounded in Python, the Grade Table
 * rounded again with `Math.round`, and the Summary tab printed one decimal —
 * so a student on 86.5 read 86%, 87% and 86.5% on three screens, because
 * Python rounds a .5 tie to even and JavaScript rounds it up.
 *
 * One decimal, and never rounded before the symbol is chosen: a score of 89.5
 * printed as "90%" sits next to the letter B, and the school's own band table
 * says 90 is an A. The teacher is left holding two facts that contradict each
 * other, and the one they can see is the wrong one.
 */
export function formatGradePercent(score: number): string {
  return `${score.toFixed(1)}%`
}
