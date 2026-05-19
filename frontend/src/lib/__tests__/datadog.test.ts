/**
 * Filter tests for ``isBenignCspViolation`` — the ``beforeSend`` hook
 * that drops known-benign CSP-Report-Only violation events before they
 * inflate the Datadog RUM error-rate panel.
 *
 * Every signature suppressed here is documented in the helper's
 * docstring; if you add a new branch there, add a matching positive
 * case here and a negative case (real CSP violation we still want to
 * see) so future edits don't silently drop real bugs.
 */

import { describe, expect, it } from "vitest"
import { isBenignCspViolation } from "../datadog"
import type { RumEvent } from "@datadog/browser-rum"

function cspError(opts: { type?: string; message: string; stack: string }) {
  // Cast: RumEvent is a discriminated union that's awkward to construct
  // by hand. The helper only reads ``type`` + ``error.{message,stack}``,
  // which we set explicitly here.
  return {
    type: opts.type ?? "error",
    error: {
      message: opts.message,
      stack: opts.stack,
    },
  } as unknown as RumEvent
}

describe("isBenignCspViolation", () => {
  it("drops Zod schemas-chunk feature-detect Function() probe", () => {
    expect(
      isBenignCspViolation(
        cspError({
          message: "csp_violation: 'eval' blocked by 'script-src' directive",
          stack:
            "script-src: 'eval' blocked by 'script-src' directive of the policy ...\n" +
            "  at <anonymous> @ https://equipbible.com/assets/schemas-ebz1wC2v.js:1:2658",
        }),
      ),
    ).toBe(true)
  })

  it("drops Vercel preview-comments overlay font fetches", () => {
    expect(
      isBenignCspViolation(
        cspError({
          message:
            "csp_violation: 'https://vercel.live/geist.woff2' blocked by 'font-src' directive",
          stack: "font-src: 'https://vercel.live/geist.woff2' blocked by 'font-src' directive ...",
        }),
      ),
    ).toBe(true)
  })

  it("keeps a real CSP violation from our own assets", () => {
    expect(
      isBenignCspViolation(
        cspError({
          message:
            "csp_violation: 'https://evil.example.com/x.js' blocked by 'script-src' directive",
          stack: "script-src ...\n  at <anonymous> @ https://equipbible.com/assets/index-XYZ.js:1:1234",
        }),
      ),
    ).toBe(false)
  })

  it("ignores non-error event types", () => {
    expect(
      isBenignCspViolation(
        cspError({
          type: "view",
          message: "csp_violation: ...",
          stack: "schemas-X.js",
        }),
      ),
    ).toBe(false)
  })

  it("ignores non-CSP error events", () => {
    expect(
      isBenignCspViolation(
        cspError({
          message: "TypeError: Cannot read properties of undefined",
          stack: "  at Foo @ https://equipbible.com/assets/schemas-ebz1wC2v.js:1:2658",
        }),
      ),
    ).toBe(false)
  })
})
