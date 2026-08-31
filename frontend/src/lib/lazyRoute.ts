import { lazy } from "react"
import type { ComponentType } from "react"

/**
 * `React.lazy` that survives a deploy landing under an open tab.
 *
 * Vite emits content-hashed chunks, and Vercel drops the previous build's
 * files. Anybody with the page already open is holding an index that names
 * chunks which no longer exist, so their next route change fetches a 404 and
 * the route dies with `Failed to fetch dynamically imported module`. It hit
 * production twice in August 2026 — six events on 2026-08-13 (`/`) and three
 * on 2026-08-17 (`/courses`) — each time around a deploy, and each time what
 * the person saw was an error screen on a healthy site.
 *
 * The fix is the ordinary one: reload once, which fetches the new index and
 * the chunk names that go with it.
 *
 * Two things this deliberately does NOT do:
 *
 *  - It does not retry the import. The chunk is gone; asking again gets the
 *    same 404 and only delays the reload.
 *  - It does not reload twice. The flag is set before reloading and cleared
 *    on any successful load, so a genuinely broken deploy — where the new
 *    index names chunks that are also missing — surfaces as an error the
 *    ErrorBoundary can show, rather than a page that reloads for ever.
 */
const RELOAD_FLAG = "equip:chunk-reloaded"

/** Vite, Webpack and Safari each word this differently. */
function isStaleChunkError(error: unknown): boolean {
  const message = error instanceof Error ? error.message : String(error)
  return (
    message.includes("Failed to fetch dynamically imported module") ||
    message.includes("error loading dynamically imported module") ||
    message.includes("Importing a module script failed")
  )
}

/** Storage throws in some privacy modes; a reload guard is not worth a crash. */
function readFlag(): boolean {
  try {
    return sessionStorage.getItem(RELOAD_FLAG) === "1"
  } catch {
    return true // Cannot guard against a loop, so do not start one.
  }
}

function writeFlag(value: boolean): void {
  try {
    if (value) sessionStorage.setItem(RELOAD_FLAG, "1")
    else sessionStorage.removeItem(RELOAD_FLAG)
  } catch {
    // Ignored: see readFlag.
  }
}

// `ComponentType<any>` mirrors React.lazy's own signature. Narrowing it to
// `unknown` would reject every route component that takes props — the legal
// pages take a `slug` — for no gain: this wrapper never touches the props.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function lazyRoute<T extends ComponentType<any>>(
  load: () => Promise<{ default: T }>,
) {
  return lazy(() =>
    load()
      .then((mod) => {
        // A load that worked means the tab is on the current build again.
        writeFlag(false)
        return mod
      })
      .catch((error: unknown) => {
        if (!isStaleChunkError(error) || readFlag()) throw error
        writeFlag(true)
        window.location.reload()
        // Never settles: the page is going away. Resolving with a placeholder
        // would flash it first, and rejecting would race the reload to the
        // ErrorBoundary.
        return new Promise<{ default: T }>(() => {})
      }),
  )
}
