const STORAGE_KEY = "equip.pendingInviteToken"

/**
 * Bridges an invite token across a full-page redirect (Google OAuth,
 * or the "confirm your email" link for a fresh email/password signup)
 * back to the accept-invite page.
 *
 * AcceptInvite calls `setPendingInviteToken` right before either
 * redirect kicks off. Once the user comes back authenticated -- to ANY
 * route, since OAuth/email-confirm both land on "/" -- App.tsx's resume
 * effect calls `takePendingInviteToken` and navigates to
 * `/invite/accept?token=...` to finish the promotion.
 */
export function setPendingInviteToken(token: string): void {
  try {
    localStorage.setItem(STORAGE_KEY, token)
  } catch {
    /* localStorage unavailable (private mode / blocked) -- the resume
       step just won't fire; the invite link still works if revisited. */
  }
}

export function takePendingInviteToken(): string | null {
  try {
    const token = localStorage.getItem(STORAGE_KEY)
    if (token) localStorage.removeItem(STORAGE_KEY)
    return token
  } catch {
    return null
  }
}
