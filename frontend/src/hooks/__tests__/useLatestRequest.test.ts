import { renderHook } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { useLatestRequest } from "../useLatestRequest"

describe("only the newest request may write its answer", () => {
  it("retires an earlier request when a later one begins", () => {
    const { result } = renderHook(() => useLatestRequest())
    const first = result.current()
    const second = result.current()
    expect(first()).toBe(false)
    expect(second()).toBe(true)
  })

  it("retires every request in flight on unmount", () => {
    const { result, unmount } = renderHook(() => useLatestRequest())
    const pending = result.current()
    unmount()
    expect(pending()).toBe(false)
  })

  it("keeps the same function across renders, so it can sit in a deps array", () => {
    const { result, rerender } = renderHook(() => useLatestRequest())
    const before = result.current
    rerender()
    expect(result.current).toBe(before)
  })
})
