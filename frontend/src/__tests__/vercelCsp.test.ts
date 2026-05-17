/**
 * Regression tests for the Content-Security-Policy-Report-Only header
 * served by `frontend/vercel.json`.
 *
 * The CSP is enforced at the CDN edge, so it has no JavaScript surface
 * we can poke at runtime -- the most reliable contract is a string-shape
 * check against `vercel.json` itself. These tests catch:
 *
 *   - someone dropping a connect-src origin (Datadog, Supabase, the API)
 *     which would silently start dropping telemetry in real browsers,
 *   - someone deleting the policy entirely (which would silently stop
 *     surfacing violations in the console), or
 *   - someone "promoting" Report-Only to enforcing CSP without updating
 *     the directive list to cover every legitimate origin (a 100%
 *     CSP-block of the live site is exactly what the report-only stage
 *     is supposed to prevent).
 *
 * If you legitimately need to remove or rename a directive, update the
 * EXPECTED_TOKENS table below in the same PR -- the test exists to make
 * those changes deliberate.
 */

import fs from "node:fs"
import path from "node:path"
import { describe, expect, it } from "vitest"

interface VercelHeader {
  key: string
  value: string
}
interface VercelHeaderRule {
  source: string
  headers: VercelHeader[]
}
interface VercelConfig {
  headers?: VercelHeaderRule[]
}

function readVercelJson(): VercelConfig {
  const root = path.resolve(__dirname, "..", "..")
  const raw = fs.readFileSync(path.join(root, "vercel.json"), "utf8")
  return JSON.parse(raw) as VercelConfig
}

function findCspReportOnly(): string {
  const cfg = readVercelJson()
  const headers = cfg.headers ?? []
  for (const rule of headers) {
    if (rule.source !== "/(.*)") continue
    for (const h of rule.headers) {
      if (h.key === "Content-Security-Policy-Report-Only") return h.value
    }
  }
  throw new Error("Content-Security-Policy-Report-Only header not found in vercel.json")
}

// Each entry: a directive token that MUST appear verbatim in the policy.
// Pick literals that are load-bearing and would not survive a sloppy edit.
const REQUIRED_TOKENS: ReadonlyArray<string> = [
  // Default fallback locked down to same-origin.
  "default-src 'self'",
  // Scripts only from same-origin -- no inline, no eval.
  "script-src 'self'",
  // Datadog RUM intake. Two host-naming patterns coexist:
  //   - subdomain form: ``us5.browser-intake-datadoghq.com`` (matched by
  //     the wildcard)
  //   - flat single-host form: ``browser-intake-us5-datadoghq.com`` (NOT
  //     a subdomain of datadoghq.com -- separate registered domain). The
  //     RUM SDK uses the flat form for US5, so we need an explicit entry.
  // Without the explicit US5 host, each RUM POST tripped a
  // ``securitypolicyviolation`` event, the RUM SDK reported it back to
  // Datadog as a frontend error, and the "RUM error spike" monitor
  // alerted on Datadog being blocked by our CSP -- a feedback loop.
  "https://*.datadoghq.com",
  "https://*.browser-intake-datadoghq.com",
  "https://browser-intake-us5-datadoghq.com",
  "https://session-replay-us5-datadoghq.com",
  // Supabase project endpoint (auth + REST + realtime websocket).
  "https://rrisqutxlkamwfhcashl.supabase.co",
  "wss://rrisqutxlkamwfhcashl.supabase.co",
  // Backend API.
  "https://api.equipbible.com",
  // YouTube embeds -- the only iframe origin we whitelist on the SPA.
  "https://www.youtube.com",
  "https://www.youtube-nocookie.com",
  // Clickjacking + base-tag injection guards.
  "frame-ancestors 'none'",
  "base-uri 'self'",
  // Form-submit hijack guard.
  "form-action 'self'",
  // Flash / Java / ActiveX -- always off.
  "object-src 'none'",
]

describe("CSP Report-Only header in vercel.json", () => {
  it("contains every required directive token", () => {
    const csp = findCspReportOnly()
    const missing = REQUIRED_TOKENS.filter((t) => !csp.includes(t))
    expect(missing).toEqual([])
  })

  it("ships as Report-Only, not enforcing", () => {
    // Belt-and-suspenders: the first pass intentionally ships in
    // report-only mode so we surface violations without breaking the
    // live site. Promoting to enforcing CSP is a deliberate later step
    // that needs its own PR and its own review.
    const cfg = readVercelJson()
    const rule = cfg.headers?.find((r) => r.source === "/(.*)")
    expect(rule).toBeDefined()
    const enforcing = rule!.headers.find((h) => h.key === "Content-Security-Policy")
    expect(enforcing).toBeUndefined()
  })

  it("does not whitelist 'unsafe-eval' anywhere", () => {
    // 'unsafe-eval' lets a string be turned back into executable code
    // (eval / new Function / setTimeout("...")). Letting it in
    // un-defeats the whole script-src protection. None of our deps
    // currently need it -- if a future dep does, this test forces a
    // conscious decision rather than a silent regression.
    const csp = findCspReportOnly()
    expect(csp).not.toMatch(/['"]?unsafe-eval['"]?/)
  })

  it("does not whitelist a wildcard host for scripts", () => {
    const csp = findCspReportOnly()
    // Pull just the script-src section so we don't trip on
    // unrelated wildcards in connect-src.
    const match = csp.match(/script-src[^;]*/)
    expect(match).not.toBeNull()
    expect(match![0]).not.toContain("*")
  })
})
