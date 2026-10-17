/**
 * "The server says this account was deleted by its owner", for the one
 * render that has to know before the profile does.
 *
 * The profile row carries `deleted_at`, and `App` shows the restore screen
 * from it. But a tab that loaded the profile *before* the deletion — the
 * laptop left open while the phone pressed the button — holds a profile
 * that still says nothing, and learns only from the API, which answers
 * every call with 403 `account.deleted`. `services/api.ts` publishes that
 * here; `App` reads it with `useSyncExternalStore`, the same shape as the
 * teacher-agreement flag.
 */
let deleted = false
const listeners = new Set<() => void>()

export function getAccountDeleted(): boolean {
  return deleted
}

export function subscribeAccountDeleted(cb: () => void): () => void {
  listeners.add(cb)
  return () => listeners.delete(cb)
}

export function publishAccountDeleted(next: boolean): void {
  if (deleted === next) return
  deleted = next
  for (const cb of listeners) cb()
}
