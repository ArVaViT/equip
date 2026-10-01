/** What a shared certificate points at: the public check, never the private page. */
import { describe, expect, it } from "vitest"

import { linkedInAddUrl, verifyUrl } from "../shareLinks"

const CERT = {
  certificate_number: "EQ-2026-000123",
  issued_at: "2026-09-30T23:30:00Z",
  course_title: "Деяния апостолов",
  archived_course_title: null,
  school_name: null,
}

describe("certificate share links", () => {
  it("shares the verification page", () => {
    expect(verifyUrl(CERT, "https://equipbible.com")).toBe("https://equipbible.com/verify/EQ-2026-000123")
  })

  it("fills LinkedIn's add-a-certification form", () => {
    const url = new URL(linkedInAddUrl(CERT, "https://equipbible.com", "UTC"))
    expect(url.origin + url.pathname).toBe("https://www.linkedin.com/profile/add")
    expect(Object.fromEntries(url.searchParams)).toEqual({
      startTask: "CERTIFICATION_NAME",
      name: "Деяния апостолов",
      organizationName: "Equip",
      certUrl: "https://equipbible.com/verify/EQ-2026-000123",
      certId: "EQ-2026-000123",
      issueYear: "2026",
      issueMonth: "9",
    })
  })

  it("names the school when the certificate has one", () => {
    const url = new URL(linkedInAddUrl({ ...CERT, school_name: "Kyiv Bible School" }, "https://equipbible.com", "UTC"))
    expect(url.searchParams.get("organizationName")).toBe("Kyiv Bible School")
  })

  it("gives the month the document prints, in the reader's zone", () => {
    // 23:30 UTC on 30 September is 1 October in Kyiv.
    const url = new URL(linkedInAddUrl(CERT, "https://equipbible.com", "Europe/Kyiv"))
    expect(url.searchParams.get("issueMonth")).toBe("10")
  })
})
