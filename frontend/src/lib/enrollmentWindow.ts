/**
 * Where a course's own enrolment window stands now: «opens» on a date still
 * ahead, «closed» once it has ended, «open» in between, `null` with no window.
 *
 * The server applies it to enrolling without a cohort
 * (`courses/enrollment.py`). One reading of it for every surface that offers
 * the button: the catalog card said «Enrollment closed» while the course page
 * and the first-run picker offered to enrol, and the server refused (2026-10-03).
 */
export type EnrollmentState = "opens" | "closed" | "open" | null

export function enrollmentState(
  start?: string | null,
  end?: string | null,
  now: Date = new Date(),
): { state: EnrollmentState; date?: Date } {
  if (!start && !end) return { state: null }
  const s = start ? new Date(start) : null
  const e = end ? new Date(end) : null
  if (s && now < s) return { state: "opens", date: s }
  if (e && now > e) return { state: "closed" }
  return { state: "open" }
}

/** Whether enrolling without a cohort is open right now. */
export function courseWindowOpen(start?: string | null, end?: string | null): boolean {
  const { state } = enrollmentState(start, end)
  return state === null || state === "open"
}
