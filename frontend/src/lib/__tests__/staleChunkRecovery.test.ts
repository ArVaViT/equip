import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { installPreloadErrorRecovery, reloadOnceFor } from '../staleChunkRecovery'

/** Mirrors how Vite's own preload helper builds the event: a plain,
 *  cancelable `Event` with the underlying error stashed on `.payload`
 *  (not `.detail` — this is not a `CustomEvent`). See
 *  https://vite.dev/guide/build#load-error-handling. */
function dispatchPreloadError(payload: unknown): boolean {
  const event = new Event('vite:preloadError', { cancelable: true }) as Event & {
    payload?: unknown
  }
  event.payload = payload
  return window.dispatchEvent(event)
}

describe('reloadOnceFor', () => {
  const reload = vi.fn()

  beforeEach(() => {
    sessionStorage.clear()
    vi.stubGlobal('location', { reload })
    reload.mockClear()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('reloads for a recognised stale-chunk error', () => {
    expect(reloadOnceFor(new Error('Failed to fetch dynamically imported module: /a.js'))).toBe(
      true,
    )
    expect(reload).toHaveBeenCalledOnce()
  })

  it('leaves an ordinary bug alone', () => {
    expect(reloadOnceFor(new TypeError("Cannot read properties of undefined (reading 'map')"))).toBe(
      false,
    )
    expect(reload).not.toHaveBeenCalled()
  })

  it('does not reload a second time within the cooldown', () => {
    reloadOnceFor(new Error('Failed to fetch dynamically imported module: /a.js'))
    reload.mockClear()
    expect(reloadOnceFor(new Error('Failed to fetch dynamically imported module: /b.js'))).toBe(
      false,
    )
    expect(reload).not.toHaveBeenCalled()
  })
})

/**
 * `installPreloadErrorRecovery` is the net under `ErrorBoundary.
 * componentDidCatch` for dynamic imports that fail outside a React render
 * frame — `useUserTour` and `useGrandTour` both fire-and-forget their
 * `driver.js` load with no `.catch`, so a stale chunk there never reaches
 * the boundary.
 */
describe('installPreloadErrorRecovery', () => {
  const reload = vi.fn()
  let uninstall: () => void

  beforeEach(() => {
    sessionStorage.clear()
    vi.stubGlobal('location', { reload })
    reload.mockClear()
    uninstall = installPreloadErrorRecovery()
  })

  afterEach(() => {
    uninstall()
    vi.unstubAllGlobals()
  })

  it.each([
    ['script', 'Failed to fetch dynamically imported module: /assets/driver-abc123.js'],
    ['stylesheet', 'Unable to preload CSS for https://equipbible.com/assets/katex-Ddr6Z9Sf.css'],
  ])('reloads once when a %s preload fails', (_label, message) => {
    const notPrevented = dispatchPreloadError(new Error(message))
    expect(reload).toHaveBeenCalledOnce()
    // Suppresses Vite's own rethrow — we've already handled it.
    expect(notPrevented).toBe(false)
  })

  it('leaves an unrecognised preload failure alone', () => {
    const notPrevented = dispatchPreloadError(new Error('CORS request did not succeed'))
    expect(reload).not.toHaveBeenCalled()
    expect(notPrevented).toBe(true)
  })

  it('does not reload a second time within the cooldown', () => {
    dispatchPreloadError(new Error('Failed to fetch dynamically imported module: /a.js'))
    expect(reload).toHaveBeenCalledOnce()
    reload.mockClear()

    dispatchPreloadError(new Error('Failed to fetch dynamically imported module: /b.js'))
    expect(reload).not.toHaveBeenCalled()
  })

  it('handles a non-Error payload without throwing', () => {
    expect(() => dispatchPreloadError('some string reason')).not.toThrow()
    expect(reload).not.toHaveBeenCalled()
  })
})
