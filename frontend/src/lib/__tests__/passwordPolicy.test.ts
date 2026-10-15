import { describe, expect, it } from "vitest"
import { PASSWORD_MIN_LENGTH, generatePassword, isLongEnough } from "@/lib/passwordPolicy"

describe("password policy", () => {
  it("keeps the minimum at the server's twelve", () => {
    // Supabase Auth is configured `password_min_length = 12`. If this
    // assertion fails, the project config moved and the form is about to
    // start accepting passwords the server will refuse — the exact defect
    // this module was written to end. Change both, or neither.
    expect(PASSWORD_MIN_LENGTH).toBe(12)
  })

  it("is not long enough one character short, and is exactly at the minimum", () => {
    expect(isLongEnough("a".repeat(PASSWORD_MIN_LENGTH - 1))).toBe(false)
    expect(isLongEnough("a".repeat(PASSWORD_MIN_LENGTH))).toBe(true)
  })
})

describe("generatePassword", () => {
  it("satisfies the rules it exists to satisfy", () => {
    const generated = generatePassword()
    expect(isLongEnough(generated)).toBe(true)
  })

  it("omits the characters people mistype", () => {
    // 200 draws over a 56-character alphabet: seeing none of these by chance
    // would be vanishingly unlikely if they were in the pool at all.
    const sample = Array.from({ length: 200 }, () => generatePassword()).join("")
    for (const confusable of ["l", "I", "1", "O", "0"]) {
      expect(sample).not.toContain(confusable)
    }
  })

  it("does not repeat itself", () => {
    const draws = new Set(Array.from({ length: 50 }, () => generatePassword()))
    expect(draws.size).toBe(50)
  })

  it("honours an explicit length", () => {
    expect(generatePassword(32)).toHaveLength(32)
  })
})
