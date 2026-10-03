import type { Cohort, Course } from "@/types"
import { enrollmentState } from "@/lib/enrollmentWindow"
import { isEnrollableCohort } from "./types"

/**
 * What pressing «Записаться на курс» can do for this reader, decided once.
 *
 * The course page used to hold this as three booleans and a click handler
 * that re-derived them; the lesson page now offers the same button at the end
 * of the preview and on the wall, and two copies of «can this person enrol,
 * and into what» is how the two would stop agreeing. The server's answer is
 * the same for both pages; so is this.
 */
export type EnrollPlan =
  /** An institute course (ADR-010): the director adds students, nobody self-enrols. */
  | { kind: "invitation" }
  /** No cohort is taking students and the course's own window is not open. */
  | { kind: "closed" }
  /** Several cohorts are open: the reader has to pick one, in the course page's dialog. */
  | { kind: "choose"; cohorts: Cohort[] }
  /** One call enrols: into the single open cohort, or into the course itself. */
  | { kind: "enroll"; cohortId?: string }

export function planEnrollment(course: Course, cohorts: Cohort[], isOwner = false): EnrollPlan {
  // Owners (teacher/admin viewing their own course) still get the normal
  // flow so they can preview as a student.
  if (course.access_mode === "institute" && !isOwner) return { kind: "invitation" }
  const open = cohorts.filter(isEnrollableCohort)
  if (open.length > 1) return { kind: "choose", cohorts: open }
  const [only] = open
  if (only) return { kind: "enroll", cohortId: only.id }
  // Without cohorts the course's own window decides, as on the server and on
  // the catalog card — which said «Enrollment closed» while the course page
  // offered to enrol (2026-10-03). With cohorts and none of them open, the
  // course is closed whatever its own window says.
  if (cohorts.length > 0) return { kind: "closed" }
  const window = enrollmentState(course.enrollment_start, course.enrollment_end)
  return window.state === null || window.state === "open" ? { kind: "enroll" } : { kind: "closed" }
}
