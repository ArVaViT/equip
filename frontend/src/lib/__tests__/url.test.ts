import { describe, it, expect } from "vitest"
import { isHttpUrl } from "../url"

describe("isHttpUrl", () => {
  it("rejects empty / nullish input", () => {
    expect(isHttpUrl(null)).toBe(false)
    expect(isHttpUrl(undefined)).toBe(false)
    expect(isHttpUrl("")).toBe(false)
  })

  it("rejects dangerous schemes that React would execute in an href", () => {
    expect(isHttpUrl("javascript:alert(1)")).toBe(false)
    // Scheme matching is case-insensitive in the browser, so this must fail too.
    expect(isHttpUrl("JavaScript:alert(1)")).toBe(false)
    expect(isHttpUrl("  javascript:alert(1)")).toBe(false)
    expect(isHttpUrl("data:text/html,<script>alert(1)</script>")).toBe(false)
    expect(isHttpUrl("vbscript:msgbox(1)")).toBe(false)
    expect(isHttpUrl("file:///etc/passwd")).toBe(false)
    expect(isHttpUrl("blob:https://x/y")).toBe(false)
  })

  it("accepts fully-qualified http(s) URLs", () => {
    expect(isHttpUrl("https://example.com/file.pdf")).toBe(true)
    expect(isHttpUrl("http://example.com")).toBe(true)
  })

  it("accepts a relative path (resolves against the safe page origin, not a script scheme)", () => {
    // window.location.origin in jsdom is http://localhost → http(s). Note a
    // base is always supplied, so a non-scheme string resolves as a relative
    // path (safe http origin) rather than failing — only explicit dangerous
    // schemes above are rejected.
    expect(isHttpUrl("/some/path")).toBe(true)
  })
})
