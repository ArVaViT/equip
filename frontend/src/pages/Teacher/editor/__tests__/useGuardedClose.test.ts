import { act, renderHook } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import { useGuardedClose } from "../useGuardedClose"

/**
 * Escape and a click beside the announcements or events dialog used to
 * throw the form away without a word. Now it asks — but only when there is
 * something typed to ask about.
 */
describe("useGuardedClose", () => {
  it("closes an untouched form without asking", async () => {
    const confirm = vi.fn(async () => true)
    const close = vi.fn()
    const reset = vi.fn()
    const { result } = renderHook(() => useGuardedClose(confirm, close))

    await act(() => result.current(false, reset))

    expect(confirm).not.toHaveBeenCalled()
    expect(close).toHaveBeenCalledTimes(1)
    expect(reset).toHaveBeenCalledTimes(1)
  })

  it("asks before closing a touched form, and keeps it when the answer is no", async () => {
    const confirm = vi.fn(async () => false)
    const close = vi.fn()
    const reset = vi.fn()
    const { result } = renderHook(() => useGuardedClose(confirm, close))

    await act(() => result.current(true, reset))

    expect(confirm).toHaveBeenCalledTimes(1)
    expect(confirm).toHaveBeenCalledWith(expect.objectContaining({ tone: "destructive" }))
    expect(close).not.toHaveBeenCalled()
    expect(reset).not.toHaveBeenCalled()
  })

  it("closes and blanks a touched form once the person says so", async () => {
    const confirm = vi.fn(async () => true)
    const close = vi.fn()
    const reset = vi.fn()
    const { result } = renderHook(() => useGuardedClose(confirm, close))

    await act(() => result.current(true, reset))

    expect(close).toHaveBeenCalledTimes(1)
    expect(reset).toHaveBeenCalledTimes(1)
  })
})
