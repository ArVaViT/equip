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

/**
 * Supabase Storage accepts only ``[A-Za-z0-9_/!.*'() &$=@;:+,?-]`` in an
 * object key. Verified against production: ``Проповедь_12_сентября.pdf``
 * was a 400 ``InvalidKey``; ``Sermon_12.pdf`` in the same path was a 200.
 * Every teacher this product has names files in Cyrillic, so this was
 * nearly every upload.
 *
 * The key doubles as the display name in the materials list, which is
 * why the letters are transliterated rather than blanked: a list of
 * ``_______.pdf`` is legal and useless.
 *
 * Exact strings throughout — no ``\b``: a JavaScript word boundary is
 * ASCII-only and would never match beside a Cyrillic letter.
 */
describe("sanitizeFileName — Cyrillic", () => {
  const STORAGE_SAFE = /^[A-Za-z0-9._()-]+$/

  it("transliterates a Russian name instead of blanking it", () => {
    expect(sanitizeFileName("Проповедь_12_сентября.pdf")).toBe("Propoved_12_sentyabrya.pdf")
  })

  it("keeps the Latin half of a mixed name and transliterates the rest", () => {
    // The em dash is not ASCII either; it and the spaces around it
    // collapse into one underscore rather than three.
    expect(sanitizeFileName("Lecture 3 — Введение.pptx")).toBe("Lecture_3_Vvedenie.pptx")
  })

  it("collapses an emoji (a surrogate pair) into a single underscore", () => {
    expect(sanitizeFileName("Урок 🎉 1.pdf")).toBe("Urok_1.pdf")
  })

  it("survives a name that is nothing but Cyrillic", () => {
    expect(sanitizeFileName("Домашнее задание")).toBe("Domashnee_zadanie")
  })

  it("transliterates a Cyrillic extension too", () => {
    expect(sanitizeFileName("Конспект.пдф")).toBe("Konspekt.pdf")
  })

  it("keeps capitals where the teacher put them", () => {
    expect(sanitizeFileName("Журнал ЖУРНАЛ.docx")).toBe("Zhurnal_ZhURNAL.docx")
  })

  it("knows the Ukrainian letters Russian lacks", () => {
    expect(sanitizeFileName("Їжак і Ґудзик є.pdf")).toBe("Yizhak_i_Gudzik_ye.pdf")
  })

  it("emits only characters Storage accepts, whatever it is given", () => {
    for (const name of [
      "Проповедь_12_сентября.pdf",
      "Фото с телефона (утро).jpg",
      "Q&A #3 [final] 100%.pdf",
      "🎉🎉🎉.pdf",
      "文件.pdf",
      "résumé.docx",
    ]) {
      expect(sanitizeFileName(name)).toMatch(STORAGE_SAFE)
    }
  })

  it("still caps the length after transliteration, keeping the extension", () => {
    // ``щ`` becomes four letters; the cap applies to the result, not the input.
    const result = sanitizeFileName("щ".repeat(60) + ".pdf")
    expect(result.length).toBeLessThanOrEqual(100)
    expect(result.endsWith(".pdf")).toBe(true)
  })
})
