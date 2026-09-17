/**
 * RUM must not index a credential carried in a URL.
 *
 * On 2026-09-16 RUM held `view.url` =
 * `https://equipbible.com/invite/accept?token=<invitation token>` for every
 * invited visitor, and `/auth/callback#access_token=…&provider_token=…
 * &refresh_token=…` for every Google sign-in. These run the real
 * `beforeSend` hook over events shaped the way RUM builds them, so a hook
 * that stops scrubbing — or a field it forgets — turns this red.
 */

import { describe, expect, it } from "vitest"
import type { RumEvent } from "@datadog/browser-rum"
import { beforeSendRum, redactSecrets } from "../datadog"

const INVITE_TOKEN = "GroKavMbyjtVv6NX9s8dRp-eshE4SLKSoXy3_h6Ym4M"
const JWT =
  "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIzM2E2OTJmYiIsInJvbGUiOiJhdXRoZW50aWNhdGVkIn0.IPiRntM9HJ7WezyqPLzigDe3_ebHpVwSxt2V_3trCvs"
const PROVIDER_TOKEN = "ya29.a0AdMD6Eh_zhgviex5o-l7n2rzMturk8G3DUsm"
const REFRESH_TOKEN = "4mqdwo5i4klm"

function send(event: Record<string, unknown>): { kept: boolean; json: string } {
  const e = event as unknown as RumEvent
  const kept = beforeSendRum(e)
  return { kept, json: JSON.stringify(e) }
}

describe("beforeSend on a RUM event", () => {
  it("removes an invitation token from the page URL, in the query or the fragment", () => {
    for (const url of [
      `https://equipbible.com/invite/accept?token=${INVITE_TOKEN}`,
      `https://equipbible.com/invite/accept#token=${INVITE_TOKEN}`,
    ]) {
      const { kept, json } = send({ type: "view", view: { id: "v", url, referrer: url } })
      expect(kept).toBe(true)
      expect(json).not.toContain(INVITE_TOKEN)
      expect(json).toContain("/invite/accept")
    }
  })

  it("removes the session a sign-in redirect leaves in the fragment", () => {
    const url =
      `https://equipbible.com/auth/callback#access_token=${JWT}&expires_at=1789503771` +
      `&expires_in=3600&provider_token=${PROVIDER_TOKEN}&refresh_token=${REFRESH_TOKEN}&sb=&token_type=bearer`
    const { json } = send({ type: "action", view: { id: "v", url } })

    expect(json).not.toContain(JWT)
    expect(json).not.toContain(PROVIDER_TOKEN)
    expect(json).not.toContain(REFRESH_TOKEN)
    // What is not a credential stays, so the view is still recognisable.
    expect(json).toContain("expires_in=3600")
    expect(json).toContain("token_type=bearer")
  })

  it("removes a token from a request URL, and from the page that made it", () => {
    const { json } = send({
      type: "resource",
      view: { id: "v", url: `https://equipbible.com/invite/accept?token=${INVITE_TOKEN}` },
      resource: { url: `https://api.equipbible.com/api/v1/invitations/token/${INVITE_TOKEN}` },
    })

    expect(json).not.toContain(INVITE_TOKEN)
    expect(json).toContain("/api/v1/invitations/token/[redacted]")
  })

  it("removes a token an error quotes in its message, stack or failed resource", () => {
    const failed = `https://api.equipbible.com/api/v1/calendar/ical/feed?token=${JWT}`
    const { kept, json } = send({
      type: "error",
      view: { id: "v", url: "https://equipbible.com/calendar" },
      error: {
        message: `Request failed: GET ${failed}`,
        stack: `Error: ${failed}\n  at x (https://equipbible.com/assets/index.js:1:1)`,
        resource: { url: failed, method: "GET", status_code: 500 },
      },
    })

    expect(kept).toBe(true)
    expect(json).not.toContain(JWT)
    expect(json).toContain("index.js:1:1")
  })

  it("still drops the benign CSP noise it dropped before", () => {
    const { kept } = send({
      type: "error",
      error: {
        message: "csp_violation: 'https://vercel.live/geist.woff2' blocked by 'font-src' directive",
        stack: "font-src ...",
      },
    })
    expect(kept).toBe(false)
  })
})

describe("what counts as a credential", () => {
  it("leaves public identifiers and look-alike parameter names alone", () => {
    for (const text of [
      "https://equipbible.com/verify/EQ-2026-000123",
      "https://equipbible.com/courses/7924a1cf-8a84-4369-91ee-1f293f0f23df?tab=grades",
      "https://equipbible.com/auth/callback#error=access_denied&error_code=otp_expired",
      "https://equipbible.com/login?error=oauth_timeout",
    ]) {
      expect(redactSecrets(text)).toBe(text)
    }
  })

  it("removes a PKCE code and a token hash", () => {
    expect(redactSecrets("https://equipbible.com/auth/callback?code=9f1c2d3e")).not.toContain("9f1c2d3e")
    expect(redactSecrets("https://equipbible.com/auth/confirm?token_hash=pkce_abc&type=signup")).toBe(
      "https://equipbible.com/auth/confirm?token_hash=[redacted]&type=signup",
    )
  })
})
