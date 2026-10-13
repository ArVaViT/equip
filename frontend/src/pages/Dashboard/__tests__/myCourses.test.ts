import { describe, expect, it } from "vitest"
import { visibleEnrollments } from "../myCourses"
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
