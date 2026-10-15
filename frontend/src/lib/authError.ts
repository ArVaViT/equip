/**
 * What a person is told when Supabase auth says no.
 *
 * The first-contact screens all used to read:
 *
 *   setServerError(supaErr.message || t("auth.loginFailed"))
 *
 * GoTrue always supplies a `message`, so the `||` never fired and the
 * translated sentence after it was dead code. What a German actually saw on
 * an otherwise entirely German sign-in page was `Invalid login credentials`,
 * and on registration `User already registered` — English prose written for
 * a server log, on the first screen the product ever shows anyone.
 *
 * The `message` is not wasted, though: it is the most specific thing we
 * have, and it is the fastest way to tell what happened. So it goes to the
 * console in dev and nowhere else.
 *
 * The sentence a person reads comes from `error.code` (GoTrue's stable
 * identifier) with `error.status` as a coarse second pass. That distinction
 * is the point of doing this properly rather than showing one generic
 * sentence: "your password is wrong" and "you have tried too many times in
 * the last minute" call for completely different next actions, and a reader
 * who is told the first when the second is true will sit there retyping a
 * password that was right all along.
 *
 * `ForgotPassword.tsx` had the shape of this right already — translate,
 * log the raw message in dev — and this is that, made reusable and given
 * the code branch.
 */

import i18n from "@/i18n/config"

/**
 * The bits of a GoTrue `AuthError` we read. Deliberately structural: the
 * thing thrown is sometimes an `AuthApiError`, sometimes a plain `Error`
 * (our own `DUPLICATE_EMAIL` sentinel), sometimes whatever a network layer
 * rejected with. Narrowing by shape handles all three without a cast that
 * claims more than we know.
 */
export interface AuthErrorish {
  message?: string
  status?: number
  code?: string
}

/**
 * GoTrue error codes we have a sentence for.
 * https://supabase.com/docs/guides/auth/debugging/error-codes
 */
const KEY_BY_CODE: Record<string, string> = {
  invalid_credentials: "auth.errors.invalidCredentials",
  email_not_confirmed: "auth.errors.emailNotConfirmed",
  over_request_rate_limit: "auth.errors.rateLimited",
  weak_password: "auth.errors.weakPassword",
  same_password: "auth.errors.samePassword",
  otp_expired: "auth.errors.linkExpired",
  session_expired: "auth.errors.linkExpired",
}

/**
 * Second pass, for the older responses that carry no `code` at all —
 * `code` only became reliable in GoTrue 2.x, and a self-hosted or lagging
 * project can still answer without it.
 */
function keyByStatus(status: number | undefined): string | null {
  if (status === 429) return "auth.errors.rateLimited"
  if (status !== undefined && status >= 500) return "auth.errors.serverError"
  return null
}

function asAuthError(err: unknown): AuthErrorish {
  return typeof err === "object" && err !== null ? (err as AuthErrorish) : {}
}

/**
 * True when the thrown error means "somebody already has this address".
 *
 * Two shapes reach us. `authService.register` throws our own
 * `DUPLICATE_EMAIL` sentinel when `signUp` succeeds with an empty
 * `identities` array (Supabase's way of not confirming an address exists to
 * an unauthenticated caller), and a project with email confirmation off
 * answers with a real `user_already_exists` instead.
 */
export function isDuplicateEmail(err: unknown): boolean {
  const e = asAuthError(err)
  return (
    e.message === "DUPLICATE_EMAIL" || e.code === "user_already_exists" || e.code === "email_exists"
  )
}

/**
 * Seconds until this address may be mailed again, when that is the refusal.
 *
 * GoTrue answers `over_email_send_rate_limit` for two different limits. One
 * is per address (`smtp_max_frequency`, a minute): «For security purposes,
 * you can only request this after 42 seconds.» The other is the whole
 * project's hourly allowance (`rate_limit_email_sent`, 30): «email rate limit
 * exceeded». The first wants a short wait; the second is an hour away, and
 * telling that person to «wait a minute» is a lie they act on. Only the
 * message tells them apart.
 */
export function emailCooldownSeconds(err: unknown): number | null {
  const e = asAuthError(err)
  if (e.code !== "over_email_send_rate_limit") return null
  const match = /after (\d+) second/.exec(e.message ?? "")
  return match ? Number(match[1]) : null
}

/** Any refusal that waiting is the answer to. */
export function isRateLimited(err: unknown): boolean {
  const e = asAuthError(err)
  return e.status === 429 || e.code === "over_request_rate_limit" || e.code === "over_email_send_rate_limit"
}

/** The account exists and its address has not been confirmed yet. */
export function isEmailNotConfirmed(err: unknown): boolean {
  return asAuthError(err).code === "email_not_confirmed"
}

/**
 * Translate an auth failure, falling back to `fallbackKey` when we have
 * nothing more specific. Never returns the server's English.
 *
 * @param fallbackKey i18n key for the screen's own "this didn't work"
 *   sentence — the one the dead `||` branch used to name.
 */
export function authErrorMessage(err: unknown, fallbackKey: string): string {
  const e = asAuthError(err)
  // Dev only: the specific thing the server said, for whoever is debugging.
  // It must not reach the screen — that is the whole defect.
  if (import.meta.env.DEV) {
    console.error("[auth]", e.code ?? e.status ?? "unknown", e.message ?? err)
  }
  if (e.code === "over_email_send_rate_limit") {
    const seconds = emailCooldownSeconds(err)
    return seconds === null ? i18n.t("auth.errors.emailQuota") : i18n.t("auth.errors.emailCooldown", { seconds })
  }
  const key = (e.code ? KEY_BY_CODE[e.code] : undefined) ?? keyByStatus(e.status) ?? fallbackKey
  return i18n.t(key)
}
