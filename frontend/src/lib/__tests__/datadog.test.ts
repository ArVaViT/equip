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

import { readFileSync } from "node:fs"
import { join } from "node:path"
import { describe, expect, it } from "vitest"
import {
  beforeSendRum,
  intakeProxyUrl,
  isAutomatedVisitor,
  isBenignCspViolation,
  isBenignWebGlRefusal,
} from "../datadog"
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

  it("drops Google Fonts blocked by font-src (extension-injected)", () => {
    // Verbatim message from a real RUM event: one visitor's browser
    // extension swapped the page fonts and produced 32 of these in a
    // single page load. We self-host via @fontsource and never request
    // gstatic, so this can't originate from our own markup.
    expect(
      isBenignCspViolation(
        cspError({
          message:
            "csp_violation: 'https://fonts.gstatic.com/s/inter/v20/UcC73FwrK3iLTeHuS_nVMrMxCp50SjIa1ZL7.woff2'" +
            " blocked by 'font-src' directive",
          stack: "font-src: 'https://fonts.gstatic.com/s/inter/v20/...' blocked by 'font-src' directive ...",
        }),
      ),
    ).toBe(true)
  })

  it("drops the Google Fonts stylesheet host too", () => {
    expect(
      isBenignCspViolation(
        cspError({
          message:
            "csp_violation: 'https://fonts.googleapis.com/css2?family=Inter' blocked by 'style-src' directive",
          stack: "style-src ...",
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

describe("isAutomatedVisitor", () => {
  const CHROME =
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.7922.34 Safari/537.36"

  it("recognises any driven browser by navigator.webdriver, whatever its user agent", () => {
    // The CI language check sent exactly this: a stock Windows Chrome UA
    // from a Playwright run — only the webdriver flag gives it away.
    expect(isAutomatedVisitor({ userAgent: CHROME, webdriver: true })).toBe(true)
  })

  it.each([
    ["headless Chrome", "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) HeadlessChrome/151.0.0.0 Safari/537.36"],
    ["Googlebot", "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"],
    ["bingbot", "Mozilla/5.0 (compatible; bingbot/2.0; +http://www.bing.com/bingbot.htm)"],
    ["Meta's indexer", "meta-webindexer/1.1 (+https://developers.facebook.com/docs/sharing/webmasters/crawler)"],
    ["ShapBot", "Mozilla/5.0 (compatible; ShapBot/0.1.0)"],
    ["Lighthouse", "Mozilla/5.0 (Linux; Android 11) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0 Mobile Safari/537.36 Chrome-Lighthouse"],
  ])("recognises %s by its user agent", (_name, userAgent) => {
    expect(isAutomatedVisitor({ userAgent })).toBe(true)
  })

  it.each([
    ["desktop Chrome", CHROME],
    ["iPhone Safari", "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1"],
    // «bot» inside a phone's model name is not a crawler: no version slash.
    ["a CUBOT phone", "Mozilla/5.0 (Linux; Android 12; CUBOT X30 Build/SP1A) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0 Mobile Safari/537.36"],
  ])("leaves %s alone", (_name, userAgent) => {
    expect(isAutomatedVisitor({ userAgent, webdriver: false })).toBe(false)
  })
})

describe("beforeSendRum noise", () => {
  it("drops three.js reporting that the browser has no WebGL", () => {
    const event = cspError({
      message:
        "THREE.WebGLRenderer: A WebGL context could not be created. Reason:  Failed to create a WebGL2 context.",
      stack: "",
    })
    expect(isBenignWebGlRefusal(event)).toBe(true)
    expect(beforeSendRum(event)).toBe(false)
  })

  it("keeps other three.js errors", () => {
    const event = cspError({ message: "THREE.WebGLRenderer: Context Lost.", stack: "" })
    expect(isBenignWebGlRefusal(event)).toBe(false)
  })

  it("drops CSP reports from Chrome's built-in page translator", () => {
    expect(
      isBenignCspViolation(
        cspError({
          message:
            "csp_violation: 'https://translate.google.com/gen204?nca=te_li&client=te_lib' blocked by 'img-src' directive",
          stack: "",
        }),
      ),
    ).toBe(true)
  })
})

describe("intakeProxyUrl", () => {
  it("sends batches to our own origin under /_e, query string intact", () => {
    expect(intakeProxyUrl({ path: "/api/v2/rum", parameters: "ddsource=browser&dd-api-key=pub123" })).toBe(
      `${window.location.origin}/_e/api/v2/rum?ddsource=browser&dd-api-key=pub123`,
    )
  })

  it("is served: vercel.json forwards /_e to the us5 intake before the SPA catch-all", () => {
    // Without the rewrite every batch would land on index.html with a 200
    // and RUM would go silent with nothing failing — so pin it here.
    const config = JSON.parse(readFileSync(join(__dirname, "..", "..", "..", "vercel.json"), "utf8")) as {
      rewrites: { source: string; destination: string }[]
    }
    const index = config.rewrites.findIndex((r) => r.source === "/_e/:path*")
    const catchAll = config.rewrites.findIndex((r) => r.destination === "/index.html")
    expect(index, "no /_e rewrite").toBeGreaterThanOrEqual(0)
    expect(index).toBeLessThan(catchAll)
    expect(config.rewrites[index]?.destination).toBe("https://browser-intake-us5-datadoghq.com/:path*")
  })
})
