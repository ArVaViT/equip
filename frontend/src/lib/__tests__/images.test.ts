import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { toProxyImage, rewriteHtmlImageSources } from "../images"

// ``toProxyImage`` caches the Supabase host on first call. We reload the module
// between tests that change VITE_SUPABASE_URL so we always observe a fresh
// resolution path, matching what a page load would do.
async function freshImages() {
  vi.resetModules()
  return (await import("../images")) as typeof import("../images")
}

describe("toProxyImage", () => {
  const SUPABASE_URL = "https://abc.supabase.co"

  beforeEach(() => {
    vi.stubEnv("VITE_SUPABASE_URL", SUPABASE_URL)
  })

  afterEach(() => {
    vi.unstubAllEnvs()
  })

  it("returns undefined for empty or null input", () => {
    expect(toProxyImage(null)).toBeUndefined()
    expect(toProxyImage("")).toBeUndefined()
    expect(toProxyImage(undefined)).toBeUndefined()
  })

  it("passes through already-proxied /img/ URLs", () => {
    expect(toProxyImage("/img/covers/123/cover.jpg")).toBe("/img/covers/123/cover.jpg")
  })

  it("rewrites Supabase Storage public URLs to /img/", async () => {
    const { toProxyImage: fn } = await freshImages()
    const input = `${SUPABASE_URL}/storage/v1/object/public/course-assets/123/cover.jpg`
    expect(fn(input)).toBe("/img/course-assets/123/cover.jpg")
  })

  it("preserves query strings when rewriting", async () => {
    const { toProxyImage: fn } = await freshImages()
    const input = `${SUPABASE_URL}/storage/v1/object/public/avatars/1/me.png?t=123`
    expect(fn(input)).toBe("/img/avatars/1/me.png?t=123")
  })

  it("leaves third-party hosts untouched", async () => {
    const { toProxyImage: fn } = await freshImages()
    expect(fn("https://images.unsplash.com/photo.jpg")).toBe(
      "https://images.unsplash.com/photo.jpg",
    )
  })

  it("rejects dangerous URL schemes (defence-in-depth)", async () => {
    const { toProxyImage: fn } = await freshImages()
    expect(fn("javascript:alert(1)")).toBeUndefined()
    expect(fn("data:text/html,<script>alert(1)</script>")).toBeUndefined()
    expect(fn("vbscript:msgbox(1)")).toBeUndefined()
  })

  it("returns original URL when Supabase URL is not configured", async () => {
    vi.stubEnv("VITE_SUPABASE_URL", "")
    const { toProxyImage: fn } = await freshImages()
    expect(fn(`${SUPABASE_URL}/storage/v1/object/public/a/b.jpg`)).toBe(
      `${SUPABASE_URL}/storage/v1/object/public/a/b.jpg`,
    )
  })

  it("ignores non-storage paths on the Supabase host", async () => {
    const { toProxyImage: fn } = await freshImages()
    const input = `${SUPABASE_URL}/rest/v1/profiles`
    expect(fn(input)).toBe(input)
  })

  it("is safe for invalid URL-like strings", () => {
    expect(toProxyImage("not a url")).toBe("not a url")
  })
})

describe("rewriteHtmlImageSources", () => {
  const SUPABASE_URL = "https://abc.supabase.co"

  beforeEach(() => {
    vi.stubEnv("VITE_SUPABASE_URL", SUPABASE_URL)
  })

  afterEach(() => {
    vi.unstubAllEnvs()
  })

  it("rewrites src attributes on <img> tags", async () => {
    const { rewriteHtmlImageSources: fn } = await freshImages()
    const html = `<img src="${SUPABASE_URL}/storage/v1/object/public/x/a.jpg" alt="a">`
    expect(fn(html)).toBe('<img src="/img/x/a.jpg" alt="a">')
  })

  it("leaves tags that reference other hosts alone", async () => {
    const { rewriteHtmlImageSources: fn } = await freshImages()
    const html = '<img src="https://cdn.example.com/a.jpg">'
    expect(fn(html)).toBe(html)
  })

  it("returns an empty string unchanged", () => {
    expect(rewriteHtmlImageSources("")).toBe("")
  })
})
