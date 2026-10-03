/**
 * The page a signed-out visitor was heading for.
 *
 * `Gate` sends a guest on a private route to `/login` with the route it
 * refused in the router state; once the person is signed in, the public gate
 * on `/login` sends them back there instead of to the dashboard. A shared
 * course link opened while logged out used to end on the dashboard, with no
 * word that the person had been going somewhere.
 *
 * Only an internal, absolute path is honoured. Router state is set by our
 * own code, but a value that could ever be influenced from outside must not
 * be able to send a fresh sign-in to another site — hence no `//host` form.
 */
export function returnPathFrom(state: unknown): string | null {
  if (!state || typeof state !== "object") return null
  const from = (state as { from?: unknown }).from
  if (typeof from !== "string") return null
  if (!from.startsWith("/") || from.startsWith("//")) return null
  // «/\evil.com» is «//evil.com» to a URL parser; refuse any backslash, and
  // anything that does not resolve to this origin.
  if (from.includes("\\")) return null
  try {
    const probe = "https://equip.invalid"
    if (new URL(from, probe).origin !== probe) return null
  } catch {
    return null
  }
  return from
}

const RETURN_KEY = "equip:returnTo"

/**
 * How long the browser-wide copy is believed. Long enough to read a mail and
 * click its link; short enough that a path remembered on a shared computer
 * does not greet whoever signs in next week.
 */
export const RETURN_PATH_TTL_MS = 60 * 60 * 1000

/**
 * Keep the return path across a full page load. Router state survives only
 * inside the app: Google sign-in and an emailed sign-in link come back through
 * `/auth/callback` in a fresh page, and the course a visitor was heading for
 * was lost there.
 *
 * Two copies. The tab's own (`sessionStorage`) is the one Google's round-trip
 * comes back to. The confirmation mail, though, opens in a tab of its own
 * with no session storage of ours, and a reader who left a lesson to create an
 * account landed on the dashboard with no word of the lesson — so the path is
 * also kept browser-wide, for an hour (`RETURN_PATH_TTL_MS`). The app does not
 * put the path into the mailed link itself: send-email builds that link from
 * its own configuration, and a path in a URL would be a value from outside.
 * Still per browser, so a link opened on another device lands on the
 * dashboard.
 */
export function rememberReturnPath(state: unknown, now: number = Date.now()): void {
  const path = returnPathFrom(state)
  if (!path) return
  try {
    sessionStorage.setItem(RETURN_KEY, path)
  } catch {
    /* storage blocked: the dashboard is the fallback */
  }
  try {
    localStorage.setItem(RETURN_KEY, JSON.stringify({ path, until: now + RETURN_PATH_TTL_MS }))
  } catch {
    /* same */
  }
}

/** The browser-wide copy, if it is still believed. Cleared on reading, whatever it held. */
function takeBrowserWide(now: number): string | null {
  const raw = localStorage.getItem(RETURN_KEY)
  localStorage.removeItem(RETURN_KEY)
  return readBrowserWide(raw, now)
}

function readBrowserWide(raw: string | null, now: number): string | null {
  if (!raw) return null
  const parsed: unknown = JSON.parse(raw)
  if (!parsed || typeof parsed !== "object") return null
  const { path, until } = parsed as { path?: unknown; until?: unknown }
  if (typeof path !== "string" || typeof until !== "number" || until <= now) return null
  return path
}

/**
 * The remembered path, once: reading it clears both copies. The tab's own
 * copy wins when there is one; the browser-wide copy is for the tab that has
 * none — the one the mail opened.
 */
export function takeReturnPath(now: number = Date.now()): string | null {
  let path: string | null = null
  try {
    path = sessionStorage.getItem(RETURN_KEY)
    sessionStorage.removeItem(RETURN_KEY)
  } catch {
    /* storage blocked */
  }
  try {
    // Always taken, so both copies are gone — a short-circuit here would
    // have left the browser-wide one for the next sign-in to find.
    const browserWide = takeBrowserWide(now)
    path ??= browserWide
  } catch {
    /* storage blocked, or not our JSON: nothing to return to */
  }
  // Validated again on the way out: storage is writable by anything on the
  // origin, and what comes back from it is not the state our code wrote.
  return returnPathFrom({ from: path })
}

/**
 * The remembered path without spending it — for a render, which may run
 * twice. Pair with ``takeReturnPath`` in an effect to spend it.
 */
export function peekReturnPath(now: number = Date.now()): string | null {
  let path: string | null = null
  try {
    path = sessionStorage.getItem(RETURN_KEY)
  } catch {
    /* storage blocked */
  }
  try {
    path ??= readBrowserWide(localStorage.getItem(RETURN_KEY), now)
  } catch {
    /* storage blocked, or not our JSON */
  }
  return returnPathFrom({ from: path })
}
