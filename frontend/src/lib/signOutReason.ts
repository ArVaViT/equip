/**
 * Why the person was signed out without asking to be.
 *
 * `services/api.ts` ends a session in two places — a token refresh that
 * failed, and an account the server reports as deactivated — and both used
 * to end the same way: the teacher is mid-sentence, the page becomes the
 * sign-in form, and nothing on it says why. The reason is kept here for the
 * one render that needs it: `Login` reads it once and clears it.
 *
 * `sessionStorage`, not `localStorage`: the notice belongs to this tab and
 * this moment. The next person on a shared device must not open the sign-in
 * form to a stale «your session expired».
 */
const KEY = "equip.auth.sign-out-reason"

export const SIGN_OUT_REASONS = ["session_expired", "account_deactivated"] as const
export type SignOutReason = (typeof SIGN_OUT_REASONS)[number]

export function rememberSignOutReason(reason: SignOutReason): void {
  try {
    window.sessionStorage.setItem(KEY, reason)
  } catch {
    // Private mode or a full quota: the notice is lost, the sign-out is not.
  }
}

/** The stored reason, if any — and it is gone once read. */
export function takeSignOutReason(): SignOutReason | null {
  try {
    const raw = window.sessionStorage.getItem(KEY)
    if (raw === null) return null
    window.sessionStorage.removeItem(KEY)
    return (SIGN_OUT_REASONS as readonly string[]).includes(raw) ? (raw as SignOutReason) : null
  } catch {
    return null
  }
}
