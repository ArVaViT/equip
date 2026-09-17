/**
 * What a sign-in link leaves in the address bar, and what becomes of it.
 *
 * Datadog RUM and Session Replay recorded
 * `/auth/callback#access_token=…&refresh_token=…` on every sign-in for as long
 * as the client ran the implicit flow. These hold the two halves of the fix:
 * the URL is emptied before anything can record it, and whatever it carried —
 * a PKCE code, an email link's token hash, or a session from a link mailed
 * before the switch — still signs the person in.
 */
import { describe, it, expect, vi, beforeEach } from "vitest"

const verifyOtp = vi.fn()
const exchangeCodeForSession = vi.fn()
const setSession = vi.fn()
vi.mock("@/lib/supabase", () => ({
  supabase: {
    auth: {
      verifyOtp: (...args: unknown[]) => verifyOtp(...args),
      exchangeCodeForSession: (...args: unknown[]) => exchangeCodeForSession(...args),
      setSession: (...args: unknown[]) => setSession(...args),
    },
  },
}))

import {
  captureAuthLanding,
  completeAuthLanding,
  hasAuthArrival,
  parseAuthArrival,
  resetAuthLandingForTests,
} from "@/lib/authLanding"

/** A stand-in for `window` whose URL we control and whose history we watch. */
function fakeWindow(href: string) {
  const replaceState = vi.fn()
  return {
    win: {
      location: { href } as Location,
      history: { state: { idx: 0 }, replaceState } as unknown as History,
    },
    replaceState,
    /** The URL the page was left on, as a path + query + fragment. */
    left: () => replaceState.mock.calls[replaceState.mock.calls.length - 1]?.[2] as string | undefined,
  }
}

const SECRETS = /access_token|refresh_token|provider_token|token_hash|code=|sb_flow_id|eyJ/

describe("captureAuthLanding", () => {
  beforeEach(() => {
    resetAuthLandingForTests()
    verifyOtp.mockReset()
    exchangeCodeForSession.mockReset()
    setSession.mockReset()
  })

  it("takes a PKCE code off the callback URL", () => {
    const w = fakeWindow("https://equipbible.com/auth/callback?code=abc-123&sb_flow_id=f1")
    expect(captureAuthLanding(w.win)).toEqual({ kind: "code", code: "abc-123", flowId: "f1" })
    expect(w.left()).toBe("/auth/callback")
    expect(hasAuthArrival()).toBe(true)
  })

  it("takes an email link's token hash out of the fragment", () => {
    const w = fakeWindow("https://equipbible.com/auth/confirm#token_hash=pkce_deadbeef&type=magiclink")
    expect(captureAuthLanding(w.win)).toEqual({
      kind: "token_hash",
      tokenHash: "pkce_deadbeef",
      type: "magiclink",
    })
    expect(w.left()).toBe("/auth/confirm")
  })

  it("wipes an old-style fragment session, provider token and all", () => {
    const w = fakeWindow(
      "https://equipbible.com/auth/reset-password#access_token=eyJhbGciOi.x.y&expires_at=1&expires_in=3600" +
        "&provider_token=ya29.secret&refresh_token=r1&token_type=bearer&type=recovery",
    )
    expect(captureAuthLanding(w.win)).toEqual({
      kind: "legacy_session",
      accessToken: "eyJhbGciOi.x.y",
      refreshToken: "r1",
      type: "recovery",
    })
    expect(w.left()).toBe("/auth/reset-password")
    expect(w.left()).not.toMatch(SECRETS)
  })

  it("keeps parameters that are not about signing in", () => {
    const w = fakeWindow("https://equipbible.com/auth/callback?code=abc&utm_source=mail")
    captureAuthLanding(w.win)
    expect(w.left()).toBe("/auth/callback?utm_source=mail")
  })

  it("wipes the reason a link failed, too", () => {
    const w = fakeWindow(
      "https://equipbible.com/auth/confirm#error=access_denied&error_code=otp_expired&error_description=Email+link+is+invalid",
    )
    expect(captureAuthLanding(w.win)).toEqual({ kind: "error", error: "access_denied", errorCode: "otp_expired" })
    expect(w.left()).toBe("/auth/confirm")
  })

  it("routes a fragment session that fell back to the bare site URL to the callback", () => {
    // GoTrue redirects to `site_url` when `redirect_to` is not allowed.
    const w = fakeWindow("https://equipbible.com/#access_token=eyJ.a.b&refresh_token=r&token_type=bearer")
    expect(captureAuthLanding(w.win)?.kind).toBe("legacy_session")
    expect(w.left()).toBe("/auth/callback")
  })

  it("leaves a `code` on an ordinary page alone", () => {
    const w = fakeWindow("https://equipbible.com/courses/abc?code=welcome")
    expect(captureAuthLanding(w.win)).toBeNull()
    expect(w.replaceState).not.toHaveBeenCalled()
    expect(hasAuthArrival()).toBe(false)
  })

  it("does nothing on a landing page without anything to take", () => {
    const w = fakeWindow("https://equipbible.com/auth/callback")
    expect(captureAuthLanding(w.win)).toBeNull()
    expect(w.replaceState).not.toHaveBeenCalled()
  })

  it("refuses a token hash with a type we never send", () => {
    const w = fakeWindow("https://equipbible.com/auth/confirm#token_hash=abc&type=sms")
    expect(captureAuthLanding(w.win)).toEqual({ kind: "malformed" })
    // …and still clears it.
    expect(w.left()).toBe("/auth/confirm")
  })
})

describe("parseAuthArrival", () => {
  it("prefers an error over anything else the URL carries", () => {
    expect(parseAuthArrival(new URLSearchParams("code=abc&error_description=nope"))?.kind).toBe("error")
  })

  it("treats half a fragment session as malformed", () => {
    expect(parseAuthArrival(new URLSearchParams("access_token=eyJ"))).toEqual({ kind: "malformed" })
  })
})

describe("completeAuthLanding", () => {
  beforeEach(() => {
    resetAuthLandingForTests()
    verifyOtp.mockReset()
    exchangeCodeForSession.mockReset()
    setSession.mockReset()
  })

  function arrive(href: string) {
    captureAuthLanding(fakeWindow(href).win)
  }

  it("verifies an email link's token hash — in any browser, no verifier needed", async () => {
    verifyOtp.mockResolvedValue({ data: { session: {} }, error: null })
    arrive("https://equipbible.com/auth/confirm#token_hash=pkce_h&type=signup")
    await expect(completeAuthLanding()).resolves.toEqual({ status: "signed-in", recovery: false })
    expect(verifyOtp).toHaveBeenCalledWith({ token_hash: "pkce_h", type: "signup" })
  })

  it("marks a recovery link as recovery", async () => {
    verifyOtp.mockResolvedValue({ data: { session: {} }, error: null })
    arrive("https://equipbible.com/auth/reset-password#token_hash=h&type=recovery")
    await expect(completeAuthLanding()).resolves.toEqual({ status: "signed-in", recovery: true })
  })

  it("exchanges a PKCE code for the flow it belongs to", async () => {
    exchangeCodeForSession.mockResolvedValue({ data: { session: {}, redirectType: null }, error: null })
    arrive("https://equipbible.com/auth/callback?code=c1&sb_flow_id=flow-7")
    await expect(completeAuthLanding()).resolves.toEqual({ status: "signed-in", recovery: false })
    expect(exchangeCodeForSession).toHaveBeenCalledWith("c1", { flowId: "flow-7" })
  })

  it("keeps a link mailed before PKCE working", async () => {
    setSession.mockResolvedValue({ data: { session: {} }, error: null })
    arrive("https://equipbible.com/auth/confirm#access_token=eyJ.a.b&refresh_token=r1&token_type=bearer&type=magiclink")
    await expect(completeAuthLanding()).resolves.toEqual({ status: "signed-in", recovery: false })
    expect(setSession).toHaveBeenCalledWith({ access_token: "eyJ.a.b", refresh_token: "r1" })
  })

  it("says a spent or stale link expired", async () => {
    verifyOtp.mockResolvedValue({
      data: { session: null },
      error: { code: "otp_expired", message: "Email link is invalid or has expired" },
    })
    arrive("https://equipbible.com/auth/confirm#token_hash=h&type=magiclink")
    await expect(completeAuthLanding()).resolves.toEqual({ status: "failed", reason: "expired" })
  })

  it("does not call an unfamiliar failure an expiry", async () => {
    exchangeCodeForSession.mockResolvedValue({
      data: { session: null },
      error: { name: "AuthPKCECodeVerifierMissingError", code: "pkce_code_verifier_not_found" },
    })
    arrive("https://equipbible.com/auth/callback?code=c1")
    await expect(completeAuthLanding()).resolves.toEqual({ status: "failed", reason: "other" })
  })

  it("reads GoTrue's own redirect error without calling it", async () => {
    arrive("https://equipbible.com/auth/callback?error=server_error&error_description=whatever")
    await expect(completeAuthLanding()).resolves.toEqual({ status: "failed", reason: "other" })
    expect(exchangeCodeForSession).not.toHaveBeenCalled()
  })

  it("spends a single-use token once, however many times the page mounts", async () => {
    verifyOtp.mockResolvedValue({ data: { session: {} }, error: null })
    arrive("https://equipbible.com/auth/confirm#token_hash=h&type=magiclink")
    const [a, b] = await Promise.all([completeAuthLanding(), completeAuthLanding()])
    expect(a).toEqual(b)
    await completeAuthLanding()
    expect(verifyOtp).toHaveBeenCalledTimes(1)
  })

  it("reports nothing when nothing arrived", async () => {
    await expect(completeAuthLanding()).resolves.toEqual({ status: "nothing" })
  })

  it("survives the client throwing", async () => {
    verifyOtp.mockRejectedValue(new TypeError("Failed to fetch"))
    arrive("https://equipbible.com/auth/confirm#token_hash=h&type=magiclink")
    await expect(completeAuthLanding()).resolves.toEqual({ status: "failed", reason: "other" })
  })
})
