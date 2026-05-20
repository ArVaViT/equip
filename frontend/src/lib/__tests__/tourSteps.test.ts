import { describe, expect, it } from "vitest"
import i18n from "@/i18n/config"
import { studentDashboardSteps, teacherDashboardSteps } from "../tourSteps"

describe("tourSteps", () => {
  it("studentDashboardSteps returns the expected sequence with resolved i18n", () => {
    const steps = studentDashboardSteps(i18n.t)
    expect(steps).toHaveLength(5)

    // Spotlit steps point at data-tour selectors, not Tailwind classes,
    // so a routine restyle of the dashboard can't silently break the
    // tour. The closing step has no element by design.
    const elements = steps.map((s) => s.element)
    expect(elements).toEqual([
      '[data-tour="my-courses"]',
      '[data-tour="verse-of-day"]',
      '[data-tour="today"]',
      '[data-tour="streak"]',
      undefined,
    ])

    // i18n must be applied — a raw "tour.student.foo.title" leaking
    // through into the popover is the bug we're most worried about
    // in this lookup chain.
    steps.forEach((step) => {
      const title = step.popover?.title ?? ""
      const description = step.popover?.description ?? ""
      expect(title).not.toMatch(/^tour\./)
      expect(description).not.toMatch(/^tour\./)
      expect(title.length).toBeGreaterThan(0)
    })
  })

  it("teacherDashboardSteps returns the expected sequence with resolved i18n", () => {
    const steps = teacherDashboardSteps(i18n.t)
    expect(steps).toHaveLength(4)

    const elements = steps.map((s) => s.element)
    expect(elements).toEqual([
      '[data-tour="new-course"]',
      '[data-tour="pending-certs"]',
      '[data-tour="courses-list"]',
      undefined,
    ])

    steps.forEach((step) => {
      const title = step.popover?.title ?? ""
      expect(title).not.toMatch(/^tour\./)
      expect(title.length).toBeGreaterThan(0)
    })
  })
})
