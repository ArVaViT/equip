import { act, renderHook } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { setDisplayTimeZone } from "../timeZone"
import { useZonedTodayKey } from "../useZonedToday"

/** A tab left open overnight kept yesterday on the dashboard's «Сегодня». */
describe("useZonedTodayKey", () => {
  afterEach(() => {
    vi.useRealTimers()
    setDisplayTimeZone(null)
  })

  it("moves on when the reader's midnight passes", () => {
    vi.useFakeTimers()
    setDisplayTimeZone("Asia/Tokyo")
    // 23:59 in Tokyo on 30 September.
    vi.setSystemTime(new Date("2026-09-30T14:59:00Z"))
    const { result } = renderHook(() => useZonedTodayKey())
    expect(result.current).toBe("2026-09-30")
    act(() => {
      vi.advanceTimersByTime(2 * 60_000)
    })
    expect(result.current).toBe("2026-10-01")
  })

  it("catches up when the tab is shown again after the laptop slept", () => {
    vi.useFakeTimers()
    setDisplayTimeZone("Asia/Tokyo")
    vi.setSystemTime(new Date("2026-09-30T14:00:00Z"))
    const { result } = renderHook(() => useZonedTodayKey())
    // The clock jumps with no timer firing, as after sleep.
    vi.setSystemTime(new Date("2026-09-30T20:00:00Z"))
    act(() => {
      document.dispatchEvent(new Event("visibilitychange"))
    })
    expect(result.current).toBe("2026-10-01")
  })
})
