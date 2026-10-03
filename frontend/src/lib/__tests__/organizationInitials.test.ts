import { describe, expect, it } from "vitest"
import { organizationInitials } from "../organizationInitials"

describe("the letters in place of a logo", () => {
  it("skips the word that says what kind of organization it is, and the quotes around the name", () => {
    // Until 2026-10-03 every church was a «Ц».
    expect(organizationInitials("Церковь «Слово Жизни»")).toBe("СЖ")
    expect(organizationInitials("Школа „Благодать“")).toBe("Б")
    expect(organizationInitials("Church of the Open Door")).toBe("OT")
    expect(organizationInitials("Місія «Нове Життя»")).toBe("НЖ")
  })

  it("keeps a one-word name as one letter, and a generic word alone as itself", () => {
    expect(organizationInitials("UCOAT")).toBe("U")
    expect(organizationInitials("Церковь")).toBe("Ц")
    expect(organizationInitials("  ")).toBe("")
  })

  it("takes two letters from a plain two-word name", () => {
    expect(organizationInitials("Slovo Zhizni")).toBe("SZ")
  })

  it("takes a whole emoji, never half of one", () => {
    expect(organizationInitials("🔥 Огонь")).toBe("🔥О")
    expect(organizationInitials("Церковь «🙏 Слово Жизни»")).toBe("🙏С")
  })
})
