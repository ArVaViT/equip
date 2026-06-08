import { describe, expect, it } from "vitest"
import { sanitizeHtml } from "../sanitize"

describe("sanitizeHtml", () => {
  it("passes through safe formatted content", () => {
    const input = "<p>Hello <strong>world</strong></p>"
    expect(sanitizeHtml(input)).toBe(input)
  })

  it("strips <script> tags entirely", () => {
    const output = sanitizeHtml("<p>ok</p><script>alert('x')</script>")
    expect(output).not.toContain("<script")
    expect(output).not.toContain("alert")
  })

  it("removes javascript: URLs from href", () => {
    const output = sanitizeHtml('<a href="javascript:alert(1)">click</a>')
    expect(output).not.toContain("javascript:")
  })

  it("removes data:text/html URLs from href", () => {
    const output = sanitizeHtml(
      '<a href="data:text/html,<script>x</script>">click</a>',
    )
    expect(output).not.toContain("data:text/html")
  })

  it("preserves data:image/png URLs", () => {
    const output = sanitizeHtml(
      '<img src="data:image/png;base64,iVBORw0KGgoAAAANS" alt="pixel">',
    )
    expect(output).toContain("data:image/png")
  })

  it("strips inline event handlers like onerror", () => {
    const output = sanitizeHtml('<img src="x" onerror="alert(1)">')
    expect(output).not.toContain("onerror")
    expect(output).not.toContain("alert")
  })

  it("strips inline onclick handlers", () => {
    const output = sanitizeHtml('<button onclick="alert(1)">hi</button>')
    // Forbidden tag — button — should also be dropped entirely.
    expect(output).not.toContain("<button")
    expect(output).not.toContain("onclick")
  })

  it("strips <style> tags", () => {
    const output = sanitizeHtml("<p>x</p><style>body{display:none}</style>")
    expect(output).not.toContain("<style")
  })

  it("keeps YouTube embed iframes", () => {
    const input = '<iframe src="https://www.youtube.com/embed/abc"></iframe>'
    const output = sanitizeHtml(input)
    expect(output).toContain("youtube.com/embed/abc")
  })

  it("keeps youtube-nocookie embed iframes", () => {
    const input =
      '<iframe src="https://www.youtube-nocookie.com/embed/abc"></iframe>'
    const output = sanitizeHtml(input)
    expect(output).toContain("youtube-nocookie.com/embed/abc")
  })

  it("removes iframes pointing to non-YouTube origins", () => {
    const input = '<iframe src="https://evil.example.com/frame"></iframe>'
    const output = sanitizeHtml(input)
    expect(output).not.toContain("evil.example.com")
    expect(output).not.toContain("<iframe")
  })

  it("preserves safe anchor tags", () => {
    const output = sanitizeHtml('<a href="https://example.com">x</a>')
    expect(output).toContain('href="https://example.com"')
  })

  it("strips style attributes", () => {
    const output = sanitizeHtml(
      '<p style="background:url(javascript:alert(1))">x</p>',
    )
    expect(output).not.toContain("style=")
  })

  it("preserves math marker data attributes so KaTeX can render", () => {
    // Without ``data-type`` / ``data-latex`` / ``data-display`` in the
    // DOMPurify allowlist the marker would lose its identity and the
    // student would see the raw ``$x^2$`` source. This pins the
    // post-merge fix from PR #504.
    const output = sanitizeHtml(
      '<p>see: <span data-type="inlineMath" data-latex="x^2" ' +
        'data-display="no">$x^2$</span>.</p>',
    )
    expect(output).toContain('data-type="inlineMath"')
    expect(output).toContain('data-latex="x^2"')
    expect(output).toContain('data-display="no"')
  })

  it("preserves <details> + <summary> for the toggle callout shape", () => {
    // The toggle callout is stored as ``<div data-callout="toggle">``
    // and rewritten to native ``<details>`` at view time. Both shapes
    // need to round-trip through DOMPurify intact — div for the
    // editor reload path, details for any case where the rewritten
    // shape is re-sanitised (e.g. pasted into another chapter).
    const output = sanitizeHtml(
      '<details data-callout="toggle" class="callout callout-toggle">' +
        "<summary>q</summary><p>a</p></details>",
    )
    expect(output).toContain("<details")
    expect(output).toContain("<summary>q</summary>")
    expect(output).toContain('data-callout="toggle"')
  })

  it("strips target from anchors so a new-tab link can't reverse-tabnab", () => {
    // The renderer deliberately drops ``target`` entirely — a sanitized
    // chapter link never opens a new browsing context, so there is no
    // window.opener for the opened page to abuse. (The only intentional
    // new-tab links are built in app code with rel="noopener noreferrer".)
    const output = sanitizeHtml('<a href="https://example.com" target="_blank">x</a>')
    expect(output).toContain('href="https://example.com"')
    expect(output).not.toContain("target")
  })
})
