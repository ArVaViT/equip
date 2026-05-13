import { renderHook, waitFor } from "@testing-library/react"
import { describe, it, expect, vi } from "vitest"
import { useAsyncData } from "@/hooks/useAsyncData"

describe("useAsyncData", () => {
  it("happy path: returns data and sets loading to false", async () => {
    const fetcher = vi.fn().mockResolvedValue({ name: "Hiren" })

    const { result } = renderHook(() => useAsyncData(fetcher, []))

    expect(result.current.loading).toBe(true)

    await waitFor(() => expect(result.current.loading).toBe(false))

    expect(result.current.data).toEqual({ name: "Hiren" })
    expect(result.current.error).toBeNull()
  })

  it("error path: sets error and leaves data undefined", async () => {
    const fetcher = vi.fn().mockRejectedValue(new Error("network failure"))

    const { result } = renderHook(() => useAsyncData(fetcher, []))

    await waitFor(() => expect(result.current.loading).toBe(false))

    expect(result.current.error).toBeInstanceOf(Error)
    expect(result.current.error?.message).toBe("network failure")
    expect(result.current.data).toBeUndefined()
  })

  it("unmount during fetch: does not update state after unmount", async () => {
    let resolvePromise!: (v: string) => void
    const fetcher = vi.fn(
      () => new Promise<string>((res) => { resolvePromise = res }),
    )

    const { result, unmount } = renderHook(() => useAsyncData(fetcher, []))

    expect(result.current.loading).toBe(true)

    unmount()
    resolvePromise("too late")

    // Give React a tick to process any stale updates
    await new Promise((r) => setTimeout(r, 0))

    // State should not have changed after unmount
    expect(result.current.data).toBeUndefined()
    expect(result.current.loading).toBe(true)
  })

  it("deps change mid-fetch: older result does not overwrite newer result", async () => {
    let resolveFirst!: (v: string) => void
    let resolveSecond!: (v: string) => void

    const firstFetch = new Promise<string>((res) => { resolveFirst = res })
    const secondFetch = new Promise<string>((res) => { resolveSecond = res })

    const fetcher = vi.fn()
      .mockReturnValueOnce(firstFetch)
      .mockReturnValueOnce(secondFetch)

    const { result, rerender } = renderHook(
      ({ dep }: { dep: number }) => useAsyncData(fetcher, [dep]),
      { initialProps: { dep: 1 } },
    )

    // Trigger second fetch by changing deps (cancels first)
    rerender({ dep: 2 })

    // Resolve second first, then first (simulates slow first request)
    resolveSecond("second result")
    resolveFirst("first result")

    await waitFor(() => expect(result.current.loading).toBe(false))

    // Newer result should win
    expect(result.current.data).toBe("second result")
  })
})