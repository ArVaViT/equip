import { describe, it, expect } from "vitest"
import { isAbsoluteHttpUrl, isHttpUrl } from "../url"

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

/**
 * The stricter question, asked of a link a teacher typed rather than one
 * the app built: is this a whole web address on its own? It mirrors
 * `normalize_meeting_url` on the server, so the meeting-link field can
 * answer while she is still looking at it.
 */
describe("isAbsoluteHttpUrl", () => {
  it("rejects empty / nullish input", () => {
    expect(isAbsoluteHttpUrl(null)).toBe(false)
    expect(isAbsoluteHttpUrl(undefined)).toBe(false)
    expect(isAbsoluteHttpUrl("")).toBe(false)
    expect(isAbsoluteHttpUrl("   ")).toBe(false)
  })

  it("rejects the schemes that would run in an href", () => {
    expect(isAbsoluteHttpUrl("javascript:alert(1)")).toBe(false)
    expect(isAbsoluteHttpUrl("JavaScript:alert(1)")).toBe(false)
    expect(isAbsoluteHttpUrl("data:text/html,<script>alert(1)</script>")).toBe(false)
    expect(isAbsoluteHttpUrl("vbscript:msgbox(1)")).toBe(false)
    expect(isAbsoluteHttpUrl("file:///etc/passwd")).toBe(false)
    expect(isAbsoluteHttpUrl("mailto:pastor@example.com")).toBe(false)
  })

  it("rejects what `isHttpUrl` accepts by resolving it against the page", () => {
    // This is the whole reason the second helper exists: a teacher
    // saying where her class meets cannot mean a path on Equip, and a
    // scheme-less host is a link that will not open.
    expect(isHttpUrl("/calendar")).toBe(true)
    expect(isAbsoluteHttpUrl("/calendar")).toBe(false)
    expect(isAbsoluteHttpUrl("zoom.us/j/1234567890")).toBe(false)
    expect(isAbsoluteHttpUrl("//evil.example.com/j/1")).toBe(false)
    expect(isAbsoluteHttpUrl("поговорим в зуме")).toBe(false)
  })

  it("rejects a host wearing another host as a costume", () => {
    expect(isAbsoluteHttpUrl("https://zoom.us@evil.example.com/j/1")).toBe(false)
    expect(isAbsoluteHttpUrl("https://user:password@evil.example.com/")).toBe(false)
  })

  it("accepts the links a teacher actually pastes", () => {
    expect(isAbsoluteHttpUrl("https://zoom.us/j/1234567890?pwd=aB3dEf")).toBe(true)
    expect(isAbsoluteHttpUrl("https://meet.google.com/abc-defg-hij")).toBe(true)
    expect(isAbsoluteHttpUrl("http://meet.example.org/room")).toBe(true)
    expect(isAbsoluteHttpUrl("https://zoom.us:8443/j/1")).toBe(true)
    // An @ outside the authority is ordinary.
    expect(isAbsoluteHttpUrl("https://zoom.us/j/1?to=pastor@example.com")).toBe(true)
  })
})
