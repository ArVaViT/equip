import type { EmailOtpType } from "@supabase/supabase-js"
import { supabase } from "@/lib/supabase"

/**
 * Everything a link that signs somebody in brings with it, and the one place
 * that turns it into a session.
 *
 * Until 2026-09 the client ran supabase-js in the implicit flow: Google, and
 * every email link through GoTrue's `/auth/v1/verify`, came back to
 * `/auth/callback#access_token=…&refresh_token=…&provider_token=…`. Datadog
 * RUM and Session Replay record the page URL, and they recorded those — 1406
 * events in 30 days, each a working session for whoever read the dashboard.
 * A `beforeSend` scrubber cannot fix that alone: Session Replay does not pass
 * through it, and the tokens were in the address bar to begin with.
 *
 * Now nothing that arrives in the URL is a session:
 *
 * - **Google** (PKCE) returns `?code=…&sb_flow_id=…`: one use, and worthless
 *   without the verifier this browser kept when the sign-in started.
 * - **Email links** (built by `supabase/functions/send-email`) carry
 *   `#token_hash=…&type=…`, verified here with `verifyOtp`. Unlike a PKCE
 *   `?code=`, that works in whichever browser opens the mail — a signup
 *   confirmed on a phone. It sits in the fragment so it never reaches a
 *   server log either.
 * - **Links already in inboxes** from before the switch still go through
 *   `/auth/v1/verify` and come back with the old fragment session. They live
 *   24 hours (`mailer_otp_exp`); they are taken here with `setSession` so they
 *   keep working until they expire, and wiped from the URL like the rest.
 *
 * `captureAuthLanding` runs in `main.tsx` before Datadog starts, so the first
 * view RUM records is already clean; the client is created with
 * `detectSessionInUrl: false` so nothing else reads the URL behind our back.
 */

/** The routes a sign-in link can land on. */
export const AUTH_LANDING_PATHS = ["/auth/callback", "/auth/confirm", "/auth/reset-password"] as const

/** Every parameter an auth redirect can put in a URL. All of them are removed. */
const AUTH_URL_PARAMS = [
  "code",
  "sb_flow_id",
  "token_hash",
  "type",
  "access_token",
  "refresh_token",
  "expires_in",
  "expires_at",
  "token_type",
  "provider_token",
  "provider_refresh_token",
  "error",
  "error_code",
  "error_description",
] as const

/**
 * The email-link types `verifyOtp` accepts. Anything else in `type` is not a
 * link we sent, and is refused rather than passed to GoTrue.
 */
const EMAIL_OTP_TYPES: readonly EmailOtpType[] = [
  "signup",
  "invite",
  "magiclink",
  "recovery",
  "email_change",
  "email",
]

export type AuthArrival =
  | { kind: "error"; error: string | null; errorCode: string | null }
  | { kind: "token_hash"; tokenHash: string; type: EmailOtpType }
  | { kind: "code"; code: string; flowId: string | null }
  | { kind: "legacy_session"; accessToken: string; refreshToken: string; type: string | null }
  | { kind: "malformed" }

export type AuthLandingResult =
  | { status: "signed-in"; recovery: boolean }
  | { status: "failed"; reason: "expired" | "other" }
  | { status: "nothing" }

let captured: AuthArrival | null = null
let pending: Promise<AuthLandingResult> | null = null

function readParams(url: URL): URLSearchParams {
  // Query first, fragment over it: GoTrue puts PKCE results in the query and
  // implicit ones (and our own email links) in the fragment. A URL never
  // legitimately carries the same key in both.
  const merged = new URLSearchParams(url.search)
  new URLSearchParams(url.hash.replace(/^#/, "")).forEach((value, key) => merged.set(key, value))
  return merged
}

/** What kind of sign-in, if any, these parameters describe. */
export function parseAuthArrival(params: URLSearchParams): AuthArrival | null {
  const error = params.get("error")
  const errorCode = params.get("error_code")
  if (error || errorCode || params.get("error_description")) {
    return { kind: "error", error, errorCode }
  }
  const tokenHash = params.get("token_hash")
  if (tokenHash) {
    const type = params.get("type")
    if (!type || !(EMAIL_OTP_TYPES as readonly string[]).includes(type)) return { kind: "malformed" }
    return { kind: "token_hash", tokenHash, type: type as EmailOtpType }
  }
  const code = params.get("code")
  if (code) return { kind: "code", code, flowId: params.get("sb_flow_id") }
  const accessToken = params.get("access_token")
  const refreshToken = params.get("refresh_token")
  if (accessToken || refreshToken) {
    if (!accessToken || !refreshToken) return { kind: "malformed" }
    return { kind: "legacy_session", accessToken, refreshToken, type: params.get("type") }
  }
  return null
}

function stripAuthParams(url: URL): string {
  const search = new URLSearchParams(url.search)
  const hash = new URLSearchParams(url.hash.replace(/^#/, ""))
  for (const key of AUTH_URL_PARAMS) {
    search.delete(key)
    hash.delete(key)
  }
  const query = search.toString()
  // A fragment that was not key=value (an in-page anchor) is left alone.
  const rawHash = url.hash.replace(/^#/, "")
  const fragment = rawHash.includes("=") ? hash.toString() : rawHash
  return `${query ? `?${query}` : ""}${fragment ? `#${fragment}` : ""}`
}

/**
 * Take whatever sign-in the current URL carries, and remove it from the URL.
 *
 * Called once, before anything records the page. On the landing routes every
 * auth parameter is taken. Anywhere else only a fragment session is — GoTrue
 * falls back to the bare site URL when a `redirect_to` is not allowed — and
 * the address becomes `/auth/callback` so the router finishes the job; a
 * `?code=` on an ordinary page could be anything, so it is left alone.
 */
export function captureAuthLanding(win: Pick<Window, "location" | "history"> = window): AuthArrival | null {
  const url = new URL(win.location.href)
  const params = readParams(url)
  const onLanding = (AUTH_LANDING_PATHS as readonly string[]).includes(url.pathname)
  const arrival = parseAuthArrival(params)
  if (!arrival) return null
  if (!onLanding && arrival.kind !== "legacy_session") return null

  captured = arrival
  pending = null
  const path = onLanding ? url.pathname : "/auth/callback"
  win.history.replaceState(win.history.state, "", `${path}${stripAuthParams(url)}`)
  return arrival
}

/** True when this page load arrived with something to sign in with. */
export function hasAuthArrival(): boolean {
  return captured !== null
}

function isExpired(err: unknown): boolean {
  const code = (err as { code?: unknown } | null)?.code
  return code === "otp_expired" || code === "flow_state_expired" || code === "flow_state_not_found"
}

async function complete(arrival: AuthArrival | null): Promise<AuthLandingResult> {
  if (!arrival) return { status: "nothing" }
  try {
    switch (arrival.kind) {
      case "error":
        // `otp_expired` covers both halves of what a person experiences as
        // "the link stopped working": past its lifetime, and already used.
        return {
          status: "failed",
          reason:
            arrival.errorCode === "otp_expired" || arrival.error === "access_denied" ? "expired" : "other",
        }
      case "malformed":
        return { status: "failed", reason: "other" }
      case "token_hash": {
        const { error } = await supabase.auth.verifyOtp({ token_hash: arrival.tokenHash, type: arrival.type })
        if (error) return { status: "failed", reason: isExpired(error) ? "expired" : "other" }
        return { status: "signed-in", recovery: arrival.type === "recovery" }
      }
      case "code": {
        const { data, error } = await supabase.auth.exchangeCodeForSession(
          arrival.code,
          arrival.flowId ? { flowId: arrival.flowId } : undefined,
        )
        if (error) return { status: "failed", reason: isExpired(error) ? "expired" : "other" }
        // Returned at runtime (auth-js keeps "/recovery" beside the verifier
        // for a PKCE password reset) but missing from the declared type.
        const redirectType = (data as { redirectType?: string | null }).redirectType
        return { status: "signed-in", recovery: redirectType === "recovery" }
      }
      case "legacy_session": {
        const { error } = await supabase.auth.setSession({
          access_token: arrival.accessToken,
          refresh_token: arrival.refreshToken,
        })
        if (error) return { status: "failed", reason: isExpired(error) ? "expired" : "other" }
        return { status: "signed-in", recovery: arrival.type === "recovery" }
      }
    }
  } catch {
    return { status: "failed", reason: "other" }
  }
}

/**
 * Turn the captured arrival into a session — once per page load.
 *
 * Every token here is single-use, and the pages that call this remount while
 * it runs (StrictMode, and `AuthContext` showing its spinner on SIGNED_IN), so
 * every caller shares the one attempt.
 */
export function completeAuthLanding(): Promise<AuthLandingResult> {
  if (!pending) pending = complete(captured)
  return pending
}

/** Test-only: forget what this "page load" captured. */
export function resetAuthLandingForTests(): void {
  captured = null
  pending = null
}
