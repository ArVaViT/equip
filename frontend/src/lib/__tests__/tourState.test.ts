import { afterEach, describe, expect, it, vi } from "vitest"
import {
  getFirstRunActive,
  getGrandTourActive,
  isCoveredByGrandTour,
  setFirstRunActive,
  setGrandTourActive,
  subscribeFirstRun,
  subscribeGrandTour,
} from "../tourState"

afterEach(() => {
  setGrandTourActive(false)
  setFirstRunActive(false)
})

describe("tourState", () => {
  it("getGrandTourActive defaults to false", () => {
    expect(getGrandTourActive()).toBe(false)
  })

  it("setGrandTourActive(true) flips the signal", () => {
    setGrandTourActive(true)
    expect(getGrandTourActive()).toBe(true)
  })

  it("subscribers are notified on flips, and only on flips", () => {
    const spy = vi.fn()
    const unsub = subscribeGrandTour(spy)

    setGrandTourActive(true)
    expect(spy).toHaveBeenCalledTimes(1)

    // No-op when value is already the same
    setGrandTourActive(true)
    expect(spy).toHaveBeenCalledTimes(1)

    setGrandTourActive(false)
    expect(spy).toHaveBeenCalledTimes(2)

    unsub()
    setGrandTourActive(true)
    expect(spy).toHaveBeenCalledTimes(2)
  })

  it("isCoveredByGrandTour matches the student-covered tour ids", () => {
    expect(isCoveredByGrandTour("student-dashboard-v1")).toBe(true)
    expect(isCoveredByGrandTour("courses-catalog-v1")).toBe(true)
    expect(isCoveredByGrandTour("calendar-v1")).toBe(true)
    expect(isCoveredByGrandTour("certificates-v1")).toBe(true)
    expect(isCoveredByGrandTour("profile-v1")).toBe(true)
  })

  it("isCoveredByGrandTour returns false for tours outside the manifest", () => {
    // Deep contextual tours (chapter view, course editor, etc.) are
    // NOT covered by the grand tour and must still fire on first
    // visit to their surfaces.
    expect(isCoveredByGrandTour("chapter-view-v1")).toBe(false)
    expect(isCoveredByGrandTour("course-detail-enrolled-v1")).toBe(false)
    expect(isCoveredByGrandTour("course-editor-v1")).toBe(false)
    expect(isCoveredByGrandTour("teacher-dashboard-v1")).toBe(false)
    expect(isCoveredByGrandTour("nonexistent")).toBe(false)
  })

  it("firstRun signal: defaults false, flips, and notifies independently from grand-tour", () => {
    expect(getFirstRunActive()).toBe(false)

    const firstRunSpy = vi.fn()
    const grandSpy = vi.fn()
    const u1 = subscribeFirstRun(firstRunSpy)
    const u2 = subscribeGrandTour(grandSpy)

    setFirstRunActive(true)
    expect(getFirstRunActive()).toBe(true)
    expect(firstRunSpy).toHaveBeenCalledTimes(1)
    // First-run flip MUST NOT cross-notify grand-tour subscribers
    // (and vice versa) — the signals are independent.
    expect(grandSpy).toHaveBeenCalledTimes(0)

    setFirstRunActive(true)
    expect(firstRunSpy).toHaveBeenCalledTimes(1) // idempotent

    setFirstRunActive(false)
    expect(firstRunSpy).toHaveBeenCalledTimes(2)

    u1()
    u2()
  })
})
