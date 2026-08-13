import { describe, expect, it } from "vitest"
import { isNewcomer, visibleEnrollments } from "../myCourses"
import type { Enrollment } from "@/types"

const enrolment = (id: string, authoredBy: string) =>
  ({ id, course: { id: `c-${id}`, created_by: authoredBy } }) as Enrollment

describe("visibleEnrollments", () => {
  it("shows a course you enrolled in even though you wrote it", () => {
    // The bug: `created_by !== user.id` hid exactly these, so the product
    // owner's own home screen said he had no courses while the catalogue said
    // "In progress" on three of them.
    const mine = [enrolment("1", "vadym"), enrolment("2", "someone-else")]
    expect(visibleEnrollments(mine)).toHaveLength(2)
  })
})

describe("isNewcomer", () => {
  it("greets somebody who genuinely has nothing", () => {
    expect(isNewcomer({ enrollments: [], loading: false, failed: false })).toBe(true)
  })

  it("never greets somebody who has courses", () => {
    expect(
      isNewcomer({ enrollments: [enrolment("1", "vadym")], loading: false, failed: false }),
    ).toBe(false)
  })

  it("stays quiet while the request is still in flight", () => {
    expect(isNewcomer({ enrollments: [], loading: true, failed: false })).toBe(false)
  })

  it("stays quiet after a failed load rather than saying the courses are gone", () => {
    // "You have nothing yet, go and pick something" is a pitch. Showing it to
    // a student whose request timed out is the same defect as every other
    // failed-read-renders-as-empty in this codebase.
    expect(isNewcomer({ enrollments: [], loading: false, failed: true })).toBe(false)
  })
})
