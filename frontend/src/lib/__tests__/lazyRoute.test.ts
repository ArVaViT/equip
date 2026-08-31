/**
 * What happens to an open tab when a deploy lands.
 *
 * Vercel drops the previous build's chunks; a tab holding the old index asks
 * for a file that is gone and the route dies with "Failed to fetch
 * dynamically imported module". Production saw it twice in August 2026,
 * both times around a deploy.
 */
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest"
import { lazyRoute } from "@/lib/lazyRoute"

const STALE = new Error(
  "Failed to fetch dynamically imported module: https://equipbible.com/assets/CoursesPage-DjbFVoeD.js",
)

/** `lazyRoute` returns a lazy component; this reaches the promise inside it. */
function loadOnce(factory: () => Promise<{ default: never }>): Promise<unknown> {
  const component = lazyRoute(factory) as unknown as {
    _payload: { _result: () => Promise<unknown> }
    _init: (payload: { _result: () => Promise<unknown> }) => unknown
  }
  return component._payload._result()
}

describe("lazyRoute", () => {
  const reload = vi.fn()

  beforeEach(() => {
    sessionStorage.clear()
    vi.stubGlobal("location", { reload })
    reload.mockClear()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it("reloads once when the chunk is gone", async () => {
    const settled = vi.fn()
    void loadOnce(() => Promise.reject(STALE)).then(settled, settled)
    await vi.waitFor(() => expect(reload).toHaveBeenCalledOnce())

    // The promise must not settle: the page is on its way out, and either
    // outcome would race the reload to the screen.
    expect(settled).not.toHaveBeenCalled()
  })

  it("does not reload a second time", async () => {
    void loadOnce(() => Promise.reject(STALE))
    await vi.waitFor(() => expect(reload).toHaveBeenCalledOnce())
    reload.mockClear()

    // Second attempt in the same tab: the new build is broken too, so this
    // has to surface rather than loop.
    await expect(loadOnce(() => Promise.reject(STALE))).rejects.toThrow(STALE)
    expect(reload).not.toHaveBeenCalled()
  })

  it("lets a real error through untouched", async () => {
    const bug = new TypeError("Cannot read properties of undefined (reading 'map')")
    await expect(loadOnce(() => Promise.reject(bug))).rejects.toThrow(bug)
    expect(reload).not.toHaveBeenCalled()
  })

  it("clears the guard after a load that works", async () => {
    sessionStorage.setItem("equip:chunk-reloaded", "1")
    await loadOnce(() => Promise.resolve({ default: (() => null) as never }))
    expect(sessionStorage.getItem("equip:chunk-reloaded")).toBeNull()
  })
})
