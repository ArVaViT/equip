import { describe, expect, it } from "vitest"

import type { Cohort, Course } from "@/types"
import { planEnrollment } from "../enrollPlan"

/**
 * One answer to «can this reader enrol, and into what», shared by the course
 * page's button and the lesson page's. The cases are the ones the course
 * page already handled, one by one, in three booleans and a click handler.
 */

const course = (over: Partial<Course> = {}): Course =>
  ({
    id: "c1",
    access_mode: "public",
    status: "published",
    enrollment_start: null,
    enrollment_end: null,
    ...over,
  }) as Course

const cohort = (over: Partial<Cohort>): Cohort =>
  ({
    status: "active",
    enrollment_start: "2000-01-01T00:00:00Z",
    enrollment_end: "2999-01-01T00:00:00Z",
    ...over,
  }) as Cohort

describe("planEnrollment", () => {
  it("enrols into the course itself when it has no cohorts and no window", () => {
    expect(planEnrollment(course(), [])).toEqual({ kind: "enroll" })
  })

  it("enrols into the one cohort that is taking students", () => {
    expect(planEnrollment(course(), [cohort({ id: "k1" }), cohort({ id: "k2", status: "completed" })])).toEqual({
      kind: "enroll",
      cohortId: "k1",
    })
  })

  it("leaves a choice between cohorts to the person", () => {
    const plan = planEnrollment(course(), [cohort({ id: "k1" }), cohort({ id: "k2" })])
    expect(plan.kind).toBe("choose")
    expect(plan.kind === "choose" && plan.cohorts.map((c) => c.id)).toEqual(["k1", "k2"])
  })

  it("is closed when every cohort has stopped taking students, whatever the course's own window says", () => {
    expect(planEnrollment(course(), [cohort({ id: "k1", enrollment_end: "2001-01-01T00:00:00Z" })])).toEqual({
      kind: "closed",
    })
  })

  it("is closed when the course's own window has shut, and open while it has not", () => {
    expect(planEnrollment(course({ enrollment_end: "2001-01-01T00:00:00Z" }), [])).toEqual({ kind: "closed" })
    expect(planEnrollment(course({ enrollment_start: "2999-01-01T00:00:00Z" }), [])).toEqual({ kind: "closed" })
    expect(planEnrollment(course({ enrollment_end: "2999-01-01T00:00:00Z" }), [])).toEqual({ kind: "enroll" })
  })

  it("is by invitation on an institute course — except for its owner, who previews as a student", () => {
    expect(planEnrollment(course({ access_mode: "institute" }), [])).toEqual({ kind: "invitation" })
    expect(planEnrollment(course({ access_mode: "institute" }), [], true)).toEqual({ kind: "enroll" })
  })
})
