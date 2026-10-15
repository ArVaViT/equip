// Patterns that indicate a stale-chunk failure: the user has an old
// index.html in memory pointing at chunk hashes that the latest deploy
// no longer publishes. The fix is to reload — fetching the fresh
// index.html immediately makes the new chunk hashes available.
//
// Each engine spells the failure differently. We match all three so a
// future Vite/Rollup tweak doesn't quietly bring back the bug:
const CHUNK_LOAD_PATTERNS: RegExp[] = [
  /failed to fetch dynamically imported module/i,
  /loading chunk \d+ failed/i,
  /chunkloaderror/i,
  /importing a module script failed/i,
  // A lazy chunk's stylesheet, not its script. Vite preloads both and
  // rejects with this when the `<link>` 404s — the shape a teacher hit on
  // 2026-09-06 when a deploy landed under their open lesson editor.
  // `lazyRoute` catches it first for route chunks; this is the net under
  // every other lazy boundary.
  /unable to preload css/i,
]

// Don't loop. If we just reloaded and still hit a chunk error, the
// fix didn't help (e.g. the user is offline) — show the manual UI
// instead of bouncing the page forever.
const RELOAD_FLAG_KEY = "errorBoundary:lastChunkReload"
const RELOAD_COOLDOWN_MS = 60_000

// Set the moment this tab asks for a reload. Until the browser tears the page
// down, code keeps running — and some of it is about to fail *because* of the
// recovery (see `reloadUnderway`).
let reloading = false

/**
 * Whether this tab has already started reloading to recover from a stale chunk.
 *
 * Vite's preload wrapper resolves a failed `import()` with `undefined` when a
 * `vite:preloadError` listener prevents its default — which is exactly what
 * `installPreloadErrorRecovery` does. The module the caller awaited is
 * therefore missing, and `React.lazy` reading `.default` off it throws
 * "Cannot read properties of undefined (reading 'default')" into the
 * ErrorBoundary while the reload is still on its way: an error screen and a
 * RUM error (2026-10-15, `/courses`) for a failure that was already handled.
 * Callers use this to wait for the reload instead.
 */
export function reloadUnderway(): boolean {
  return reloading
}

/**
 * Start the reload. Every recovery path goes through here so `reloadUnderway`
 * is true however the reload was asked for.
 */
export function startReload(): void {
  reloading = true
  window.location.reload()
}

/** Tests only: a fresh tab. */
export function resetReloadState(): void {
  reloading = false
}

function isChunkLoadError(error: Error): boolean {
  const message = error.message || ""
  return CHUNK_LOAD_PATTERNS.some((re) => re.test(message))
}

function recentlyReloaded(): boolean {
  try {
    const last = parseInt(sessionStorage.getItem(RELOAD_FLAG_KEY) ?? "0", 10)
    return Number.isFinite(last) && Date.now() - last < RELOAD_COOLDOWN_MS
  } catch {
    return false
  }
}

function markReloaded() {
  try {
    sessionStorage.setItem(RELOAD_FLAG_KEY, String(Date.now()))
  } catch {
    // sessionStorage can throw in Safari private mode etc. Worst case
    // we lose the loop guard — better than crashing the recovery path.
  }
}

/**
 * Reload once for a recognised stale-chunk error, sharing the cooldown
 * above so every call site — `ErrorBoundary.componentDidCatch` and
 * `installPreloadErrorRecovery` below — draws from the same guard and
 * can't compound into a loop between them.
 *
 * Returns whether it reloaded, so a caller that has its own error to
 * rethrow (or suppress) can decide based on that.
 */
export function reloadOnceFor(error: Error): boolean {
  if (!isChunkLoadError(error) || recentlyReloaded()) return false
  markReloaded()
  startReload()
  return true
}

/**
 * Net under `ErrorBoundary.componentDidCatch` for stale-chunk failures
 * that never reach a React render frame.
 *
 * `componentDidCatch` only sees a chunk-load error if the rejected import()
 * promise is eventually *thrown* while React is rendering — true for
 * `lazyRoute()`-wrapped routes, but not for the handful of fire-and-forget
 * dynamic imports in this app that resolve outside render (`useUserTour`'s
 * `void buildDriver().then(...)`, `useGrandTour`'s `void pending.then(...)`
 * — both load `driver.js` on demand and neither attaches a `.catch`). A
 * stale chunk there becomes an unhandled rejection the boundary never sees.
 *
 * Vite's own preload/import wrapper dispatches `vite:preloadError` on
 * `window` right before it would otherwise rethrow the failure (see
 * https://vite.dev/guide/build#load-error-handling), which is exactly the
 * hook needed to recover before that happens — for *every* dynamic import
 * in the app, not just the ones wired through `componentDidCatch`. Reuses
 * `reloadOnceFor` so both paths share one cooldown.
 *
 * Returns an unsubscribe function (unused in `main.tsx` — the listener lives
 * for the tab's lifetime — but it lets tests install and tear down cleanly).
 */
export function installPreloadErrorRecovery(): () => void {
  const handler = (event: Event) => {
    const payload = (event as Event & { payload?: unknown }).payload
    const error = payload instanceof Error ? payload : new Error(String(payload))
    // Only swallow the event (and the rethrow Vite would otherwise do) when
    // we actually act on it. Anything we don't recognise, or a repeat while
    // the cooldown is still active, is left to surface exactly as it would
    // without this listener — an unhandled rejection Datadog RUM captures.
    if (reloadOnceFor(error)) {
      event.preventDefault()
    }
  }
  window.addEventListener("vite:preloadError", handler)
  return () => window.removeEventListener("vite:preloadError", handler)
}
