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

/**
 * "This browser asked for a restore link for this account" — so arriving
 * back from the link restores at once instead of asking a second time. A
 * day, like the link itself (`mailer_otp_exp`). Storage that throws or is
 * empty (a private window, an in-app browser) only costs that one click:
 * the screen's button restores just the same.
 */
const RESTORE_REQUESTED_PREFIX = "equip.account.restore-requested"
const RESTORE_REQUEST_TTL_MS = 24 * 60 * 60 * 1000

export function rememberRestoreRequested(userId: string, now: number = Date.now()): void {
  try {
    localStorage.setItem(`${RESTORE_REQUESTED_PREFIX}.${userId}`, String(now))
  } catch {
    /* storage unavailable: the button still works */
  }
}

export function wasRestoreRequested(userId: string, now: number = Date.now()): boolean {
  try {
    const at = Number(localStorage.getItem(`${RESTORE_REQUESTED_PREFIX}.${userId}`))
    return Number.isFinite(at) && at > 0 && now - at >= 0 && now - at < RESTORE_REQUEST_TTL_MS
  } catch {
    return false
  }
}

export function forgetRestoreRequested(userId: string): void {
  try {
    localStorage.removeItem(`${RESTORE_REQUESTED_PREFIX}.${userId}`)
  } catch {
    /* nothing to forget */
  }
}
