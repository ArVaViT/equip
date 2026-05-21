import { describe, expect, it } from "vitest"

import { sanitizeFileName } from "../storage"

describe("sanitizeFileName", () => {
  it("returns short filenames unchanged", () => {
    expect(sanitizeFileName("notes.pdf")).toBe("notes.pdf")
  })

  it("replaces path-illegal characters with underscores", () => {
    expect(sanitizeFileName('what:is/this\\file*.txt')).toBe("what_is_this_file_.txt")
  })

  it("collapses whitespace runs into single underscores", () => {
    expect(sanitizeFileName("two   spaces.pdf")).toBe("two_spaces.pdf")
  })

  it("preserves the extension when the name exceeds the length cap", () => {
    // Regression: the previous implementation sliced to 100 chars AFTER
    // the special-char replace and dropped the extension. Result was a
    // path like ``${chapterId}/${ts}-very-long-...na`` with no .pdf,
    // breaking download MIME sniffing.
    const stem = "a".repeat(200)
    const result = sanitizeFileName(`${stem}.pdf`)
    expect(result.endsWith(".pdf")).toBe(true)
    expect(result.length).toBeLessThanOrEqual(100)
  })

  it("hard-truncates names that have no extension", () => {
    const result = sanitizeFileName("x".repeat(150))
    expect(result.length).toBe(100)
    expect(result).toBe("x".repeat(100))
  })

  it("hard-truncates when the extension itself is pathologically long", () => {
    // ``.${'y'.repeat(120)}`` is itself longer than the cap. Falling
    // back to a hard truncate beats emitting a zero-length stem.
    const result = sanitizeFileName("z" + "." + "y".repeat(120))
    expect(result.length).toBe(100)
  })

  it("treats a trailing dot as no extension", () => {
    const result = sanitizeFileName("name." + "a".repeat(150))
    expect(result.length).toBeLessThanOrEqual(100)
  })
})
