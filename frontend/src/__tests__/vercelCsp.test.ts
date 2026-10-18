/**
 * Regression tests for the Content-Security-Policy header served by
 * `frontend/vercel.json`.
 *
 * Promoted from Report-Only to enforcing for the June 2026 launch:
 * Report-Only had been live long enough to surface any violation via
 * Datadog RUM's ``securitypolicyviolation`` capture, none persisted
 * (the US5 host-pattern caveat noted below was caught during that
 * window and fixed). Enforcing now gives ~2 weeks of real-traffic
 * observation before the launch ad spend goes live.
 *
 * The CSP is applied at the CDN edge, so it has no JavaScript surface
 * we can poke at runtime -- the most reliable contract is a string-shape
 * check against `vercel.json` itself. These tests catch:
 *
 *   - someone dropping a connect-src origin (Datadog, Supabase, the API)
 *     which would now hard-block telemetry / API calls in real browsers,
 *   - someone deleting the policy entirely (silently removing every
 *     enforced directive),
 *   - someone re-introducing ``'unsafe-eval'`` or a wildcard script
 *     source (which would un-defeat the whole script-src protection).
 *
 * If you legitimately need to remove or rename a directive, update the
 * EXPECTED_TOKENS table below in the same PR -- the test exists to make
 * those changes deliberate.
 */

import fs from "node:fs"
import path from "node:path"
import { describe, expect, it } from "vitest"

// `vercel.json` is written as `routes` (see scripts/__tests__/vercel-config.test.ts
// for why); the site-wide security headers are the `continue: true` route
// that matches every path, before the filesystem check.
interface VercelRoute {
  src?: string
  headers?: Record<string, string>
}
interface VercelConfig {
  routes?: VercelRoute[]
}

const SITE_WIDE_SRC = "^(?:/(.*))$"

function readVercelJson(): VercelConfig {
  const root = path.resolve(__dirname, "..", "..")
  const raw = fs.readFileSync(path.join(root, "vercel.json"), "utf8")
  return JSON.parse(raw) as VercelConfig
}

function siteWideHeaders(): Record<string, string> | undefined {
  return readVercelJson().routes?.find((r) => r.src === SITE_WIDE_SRC)?.headers
}

function findCsp(): string {
  const csp = siteWideHeaders()?.["Content-Security-Policy"]
  if (csp === undefined) throw new Error("Content-Security-Policy header not found in vercel.json")
  return csp
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
  // Supabase endpoint (auth + REST + realtime websocket + public
  // storage images): the one project there is. It used to be
  // ``*.supabase.co`` "so a local or preview project could differ" --
  // but local runs and the e2e suite are served by ``vite preview``,
  // where this header never applies, and Preview deploys are built
  // against the production project (docs/DEPLOYMENT.md, "Known gaps").
  // The wildcard only let an injected request reach somebody else's
  // project. The ref is already hard-coded in the ``/img`` rewrites below.
  "https://rrisqutxlkamwfhcashl.supabase.co",
  "wss://rrisqutxlkamwfhcashl.supabase.co",
  // Backend API (production).
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

describe("CSP header in vercel.json", () => {
  it("contains every required directive token", () => {
    const csp = findCsp()
    const missing = REQUIRED_TOKENS.filter((t) => !csp.includes(t))
    expect(missing).toEqual([])
  })

  it("ships as enforcing, not Report-Only", () => {
    // Belt-and-suspenders: launch hardening — the first pass shipped
    // Report-Only; this asserts we have actually flipped to enforcing
    // and haven't accidentally re-introduced the report-only key
    // (which would silently re-disable every directive in production).
    const headers = siteWideHeaders()
    expect(headers).toBeDefined()
    expect(headers!["Content-Security-Policy"]).toBeDefined()
    expect(headers!["Content-Security-Policy-Report-Only"]).toBeUndefined()
  })

  it("does not whitelist 'unsafe-eval' anywhere", () => {
    // 'unsafe-eval' lets a string be turned back into executable code
    // (eval / new Function / setTimeout("...")). Letting it in
    // un-defeats the whole script-src protection. None of our deps
    // currently need it -- if a future dep does, this test forces a
    // conscious decision rather than a silent regression.
    const csp = findCsp()
    expect(csp).not.toMatch(/['"]?unsafe-eval['"]?/)
  })

  it("names the Supabase project instead of every Supabase project", () => {
    const csp = findCsp()
    expect(csp).not.toContain("*.supabase.co")
    for (const directive of ["img-src", "connect-src"]) {
      const match = csp.match(new RegExp(`${directive}[^;]*`))
      expect(match).not.toBeNull()
      expect(match![0]).toContain("https://rrisqutxlkamwfhcashl.supabase.co")
    }
  })

  it("does not whitelist a wildcard host for scripts", () => {
    const csp = findCsp()
    // Pull just the script-src section so we don't trip on
    // unrelated wildcards in connect-src.
    const match = csp.match(/script-src[^;]*/)
    expect(match).not.toBeNull()
    expect(match![0]).not.toContain("*")
  })
})
