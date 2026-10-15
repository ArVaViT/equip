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
import { installPreloadErrorRecovery, resetReloadState } from "@/lib/staleChunkRecovery"

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
    resetReloadState()
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
    // The reloaded page starts with fresh module state; only sessionStorage
    // carries over.
    resetReloadState()

    // Second attempt in the same tab: the new build is broken too, so this
    // has to surface rather than loop.
    await expect(loadOnce(() => Promise.reject(STALE))).rejects.toThrow(STALE)
    expect(reload).not.toHaveBeenCalled()
  })

  /**
   * The failure a teacher actually hit on 2026-09-06, in the lesson editor,
   * mid-deploy: Vite preloads a lazy chunk's stylesheets before running the
   * chunk, and `katex.min.css` — a static import of `RichTextEditor` — was
   * one of the editor chunk's preloads. Same cause as the three JS
   * spellings above, different words, and until this test they were not
   * matched: the route threw and the person saw an error screen.
   */
  it("reloads when the chunk's stylesheet is gone", async () => {
    const cssGone = new Error(
      "Unable to preload CSS for https://equipbible.com/assets/katex-Ddr6Z9Sf.css",
    )
    const settled = vi.fn()
    void loadOnce(() => Promise.reject(cssGone)).then(settled, settled)
    await vi.waitFor(() => expect(reload).toHaveBeenCalledOnce())
    expect(settled).not.toHaveBeenCalled()
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

/**
 * The other half of the recovery: Vite's own `vite:preloadError` event, which
 * `installPreloadErrorRecovery` answers by reloading and preventing Vite's
 * rethrow. Vite's wrapper then *resolves* — with `undefined` — and the route
 * read `.default` off nothing: "Cannot read properties of undefined (reading
 * 'default')" reached the ErrorBoundary while the reload was on its way
 * (RUM, 2026-10-15, `/courses`).
 */
describe("lazyRoute after Vite's preload listener took the failure", () => {
  const reload = vi.fn()
  let uninstall: () => void

  /** What Vite's `__vitePreload` does when the chunk 404s. */
  function vitePreloadFails(): void {
    const event = new Event("vite:preloadError", { cancelable: true }) as Event & { payload?: unknown }
    event.payload = STALE
    window.dispatchEvent(event)
    if (!event.defaultPrevented) throw STALE
  }

  beforeEach(() => {
    sessionStorage.clear()
    resetReloadState()
    vi.stubGlobal("location", { reload })
    reload.mockClear()
    uninstall = installPreloadErrorRecovery()
  })

  afterEach(() => {
    uninstall()
    vi.unstubAllGlobals()
  })

  it("waits for the reload instead of handing React an undefined module", async () => {
    const settled = vi.fn()
    void loadOnce(async () => {
      vitePreloadFails()
      return undefined as unknown as { default: never }
    }).then(settled, settled)

    await vi.waitFor(() => expect(reload).toHaveBeenCalledOnce())
    await new Promise((r) => setTimeout(r, 0))
    expect(settled).not.toHaveBeenCalled()
  })

  it("waits for it too when the loader picks a named export off the missing module", async () => {
    // App.tsx: `import("@/components/firstRun").then((m) => ({ default: m.FirstRunFlow }))`.
    const settled = vi.fn()
    void loadOnce(async () => {
      vitePreloadFails()
      const m = undefined as unknown as { FirstRunFlow: never }
      return { default: m.FirstRunFlow }
    }).then(settled, settled)

    await vi.waitFor(() => expect(reload).toHaveBeenCalledOnce())
    await new Promise((r) => setTimeout(r, 0))
    expect(settled).not.toHaveBeenCalled()
  })
})
