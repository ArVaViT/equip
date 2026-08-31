/**
 * One definition of "earned", because two screens invented their own.
 *
 * A row in `certificates` is a request: pending, teacher-approved, rejected
 * or awarded. Counting rows and calling the total "earned" produced the same
 * untruth twice, independently — "14 certificates earned" above fourteen
 * rejections on the certificates page, and "14 Certificates Earned" beside
 * "0 Courses Completed" in the profile. Fixing the first did not fix the
 * second.
 */
import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import { describe, expect, it } from "vitest"

import { countAwarded, isAwardedCertificate } from "@/lib/certificates"

describe("what counts as earned", () => {
  it("counts an awarded certificate", () => {
    expect(isAwardedCertificate({ status: "approved" })).toBe(true)
  })

  it("does not count a request that is still moving", () => {
    expect(isAwardedCertificate({ status: "pending" })).toBe(false)
    expect(isAwardedCertificate({ status: "teacher_approved" })).toBe(false)
  })

  it("does not count a refusal", () => {
    // The exact shape of all fourteen rows in production.
    expect(isAwardedCertificate({ status: "rejected" })).toBe(false)
    expect(countAwarded([{ status: "rejected" }, { status: "rejected" }])).toBe(0)
  })

  it("counts only the awarded ones in a mixed list", () => {
    expect(
      countAwarded([
        { status: "approved" },
        { status: "rejected" },
        { status: "pending" },
        { status: "approved" },
      ]),
    ).toBe(2)
  })
})

describe("every screen that reports a certificate total", () => {
  const SCREENS = [
    {
      path: "src/pages/Certificates/CertificatesPage.tsx",
      // The exact line that produced "14 certificates earned".
      forbidden: /count:\s*certificates\.length/,
    },
    {
      path: "src/pages/Profile/ProfilePage.tsx",
      // `certs.length` is still legitimate here — it decides whether to link
      // to the full list, and somebody whose requests were all refused should
      // still be able to open it. What must never come from a length again is
      // the number labelled "earned".
      forbidden: /setCertificateCount\([^)]*\.length/,
    },
  ]

  for (const { path, forbidden } of SCREENS) {
    it(`${path.split("/").pop()} uses the shared definition`, () => {
      const code = readFileSync(resolve(process.cwd(), path), "utf8")
      expect(code).toContain("countAwarded")
      expect(code).not.toMatch(forbidden)
    })
  }
})
