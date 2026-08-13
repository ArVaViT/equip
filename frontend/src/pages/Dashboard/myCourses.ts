import type { Enrollment } from "@/types"

/**
 * Which enrolments the home screen shows, and when it may call somebody new.
 *
 * Extracted because the rule was two expressions inside a component, and one
 * of them was wrong in a way nobody could see from the code: enrolments on
 * courses you had written were filtered out, with no comment saying why. A
 * teacher enrolled in their own three courses therefore opened the home screen
 * and read "pick a subject that draws you and begin" — under a "recently
 * viewed" strip listing two of them, while the catalogue said "In progress" on
 * all three. Three screens, three different accounts of the same fact.
 *
 * Checked before removing the filter: creating a course does not auto-enrol
 * its author, so every enrolment is deliberate and there was never a stream of
 * unwanted rows to protect anybody from.
 */
export function visibleEnrollments(enrollments: Enrollment[]): Enrollment[] {
  return enrollments
}

/**
 * `true` only for somebody who genuinely has nothing yet.
 *
 * Deliberately false while loading and after a failed load: the welcome
 * surface is a pitch to a newcomer, and showing it to a student whose request
 * timed out tells them their courses are gone.
 */
export function isNewcomer({
  enrollments,
  loading,
  failed,
}: {
  enrollments: Enrollment[]
  loading: boolean
  failed: boolean
}): boolean {
  return !loading && !failed && visibleEnrollments(enrollments).length === 0
}
