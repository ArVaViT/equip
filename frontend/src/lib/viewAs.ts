/**
 * "View as": a platform admin sees Equip as another person, read-only.
 *
 * The server is the lock (backend ``app.services.view_as``): it refuses
 * every write that carries the header and runs reads in a READ ONLY
 * transaction. This module is the courtesy on top — it sends the header,
 * refuses writes before they leave the browser, and says so — so that a
 * page which tries to save something shows a clear message instead of an
 * error.
 *
 * Kept in sessionStorage: one tab, gone when the tab closes.
 */

export const VIEW_AS_HEADER = "X-View-As"
const KEY = "equip.view-as"

export interface ViewAsPerson {
  id: string
  email: string
  full_name: string | null
  role: string
}

export interface ViewAs {
  id: string
  expires_at: string
  person: ViewAsPerson
}

export class ViewAsReadOnlyError extends Error {
  constructor() {
    super("Read-only view: nothing can be changed")
    this.name = "ViewAsReadOnlyError"
  }
}

function read(): ViewAs | null {
  try {
    const raw = sessionStorage.getItem(KEY)
    return raw ? (JSON.parse(raw) as ViewAs) : null
  } catch {
    return null
  }
}

/** The view in force, or null. An expired one is cleared on the way out. */
export function activeViewAs(): ViewAs | null {
  const view = read()
  if (!view) return null
  if (Date.parse(view.expires_at) <= Date.now()) {
    clearViewAs()
    return null
  }
  return view
}

export function setViewAs(view: ViewAs): void {
  try {
    sessionStorage.setItem(KEY, JSON.stringify(view))
  } catch {
    // Storage refused: the view simply does not start.
  }
}

export function clearViewAs(): void {
  try {
    sessionStorage.removeItem(KEY)
  } catch {
    // Nothing to clear.
  }
}

/** Throw before a write or upload while a view is on. */
export function refuseWhileViewingAs(): void {
  if (activeViewAs()) throw new ViewAsReadOnlyError()
}
