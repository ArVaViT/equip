/**
 * Where an accepted invitation leaves you, and what the dashboard knows.
 *
 * Both of these come from walking the real thing: "when onboarding
 * finished I was on the home page with no courses, and when I refreshed
 * the course appeared". Two separate faults behind one symptom —
 * the dashboard never re-read its enrollments, and the accept screen
 * sent people to a dashboard rather than to the course they had just
 * been given.
 */

import { describe, expect, it, vi } from "vitest"
import {
  enrollmentsChanged,
  enrollmentsVersion,
  subscribeEnrollments,
} from "@/lib/enrollmentsChanged"

describe("the signal that enrollments changed", () => {
  it("moves its version and tells every subscriber", () => {
    const before = enrollmentsVersion()
    const listener = vi.fn()
    const unsubscribe = subscribeEnrollments(listener)

    enrollmentsChanged()

    expect(enrollmentsVersion()).toBeGreaterThan(before)
    expect(listener).toHaveBeenCalledTimes(1)
    unsubscribe()
  })

  it("stops telling a subscriber that unsubscribed", () => {
    const listener = vi.fn()
    subscribeEnrollments(listener)()

    enrollmentsChanged()

    expect(listener).not.toHaveBeenCalled()
  })

  it("carries no data, only the fact", () => {
    // The version is a number and nothing else: whoever hears it
    // re-reads from the server, so there is one source of truth and a
    // stale render is not expressible.
    expect(typeof enrollmentsVersion()).toBe("number")
  })
})
