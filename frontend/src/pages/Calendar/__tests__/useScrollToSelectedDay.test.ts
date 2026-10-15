import { act, renderHook } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"

import { useScrollToSelectedDay } from "../useScrollToSelectedDay"

/**
 * On a phone the day panel sits under a grid taller than the screen, so a
 * tap on a day looked like nothing had happened. After a tap the panel is
 * scrolled to — after a tap only, and only where it is below the grid.
 */

function matchMediaReporting(matches: boolean) {
  Object.defineProperty(window, "matchMedia", {
    configurable: true,
    writable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches: query.includes("max-width") ? matches : false,
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    })),
  })
}

function mountPanel(result: { current: ReturnType<typeof useScrollToSelectedDay> }) {
  const panel = document.createElement("div")
  const scrollIntoView = vi.fn()
  panel.scrollIntoView = scrollIntoView
  ;(result.current.panelRef as { current: HTMLDivElement | null }).current = panel
  return scrollIntoView
}

describe("useScrollToSelectedDay", () => {
  afterEach(() => {
    // jsdom ships without matchMedia; leave it that way for the next file.
    delete (window as { matchMedia?: unknown }).matchMedia
  })

  it("scrolls the panel into view on a narrow screen after a tap on another day", () => {
    matchMediaReporting(true)
    let selected: Date | null = new Date(2026, 9, 3)
    const { result, rerender } = renderHook(() => useScrollToSelectedDay(selected, (d) => (selected = d)))
    const scrollIntoView = mountPanel(result)
    expect(scrollIntoView).not.toHaveBeenCalled()

    act(() => result.current.selectByTap(new Date(2026, 9, 10)))
    rerender()
    expect(scrollIntoView).toHaveBeenCalledWith({ behavior: "smooth", block: "start" })
  })

  it("leaves the page alone when the day changes without a tap", () => {
    matchMediaReporting(true)
    let selected: Date | null = new Date(2026, 9, 3)
    const { result, rerender } = renderHook(() => useScrollToSelectedDay(selected, (d) => (selected = d)))
    const scrollIntoView = mountPanel(result)

    // The month arrow, «Today»: not a tap on a day.
    selected = new Date(2026, 10, 1)
    rerender()
    expect(scrollIntoView).not.toHaveBeenCalled()
  })

  it("does not scroll a wide screen, where the panel is already beside the grid", () => {
    matchMediaReporting(false)
    let selected: Date | null = new Date(2026, 9, 3)
    const { result, rerender } = renderHook(() => useScrollToSelectedDay(selected, (d) => (selected = d)))
    const scrollIntoView = mountPanel(result)

    act(() => result.current.selectByTap(new Date(2026, 9, 10)))
    rerender()
    expect(scrollIntoView).not.toHaveBeenCalled()
  })

  it("survives a browser without scrollIntoView, and a tap on the day already open", () => {
    matchMediaReporting(true)
    let selected: Date | null = new Date(2026, 9, 3)
    const { result, rerender } = renderHook(() => useScrollToSelectedDay(selected, (d) => (selected = d)))
    ;(result.current.panelRef as { current: HTMLDivElement | null }).current = document.createElement("div")

    expect(() => {
      act(() => result.current.selectByTap(new Date(2026, 9, 3)))
      rerender()
      act(() => result.current.selectByTap(new Date(2026, 9, 10)))
      rerender()
    }).not.toThrow()
  })
})
