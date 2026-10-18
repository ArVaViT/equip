/**
 * `public/.well-known/security.txt` (RFC 9116).
 *
 * The file says where to report a vulnerability, and it must say the same
 * thing as SECURITY.md: two channels that disagree are worse than one.
 * It also carries a date after which a reader is told to distrust it, so
 * this test fails a month before that date rather than on it.
 *
 * The SPA fallback in `vercel.json` already leaves `/.well-known/` alone
 * (pinned in `scripts/__tests__/vercel-config.test.ts`), so the file is
 * served from the filesystem as written.
 */
import fs from "node:fs"
import path from "node:path"
import { describe, expect, it } from "vitest"

const FRONTEND = path.resolve(__dirname, "..", "..")
const SECURITY_TXT = fs.readFileSync(path.join(FRONTEND, "public", ".well-known", "security.txt"), "utf8")
const SECURITY_MD = fs.readFileSync(path.join(FRONTEND, "..", "SECURITY.md"), "utf8")

function fields(name: string): string[] {
  return SECURITY_TXT.split("\n")
    .filter((line) => line.startsWith(`${name}:`))
    .map((line) => line.slice(name.length + 1).trim())
}

describe("security.txt", () => {
  it("names the channels SECURITY.md names", () => {
    const contacts = fields("Contact")
    expect(contacts).toContain("mailto:supportequip@gmail.com")
    expect(contacts).toContain("https://github.com/ArVaViT/equip/security/advisories/new")
    expect(SECURITY_MD).toContain("supportequip@gmail.com")
    expect(SECURITY_MD).toContain("https://github.com/ArVaViT/equip/security/advisories/new")
  })

  it("has exactly one Expires, at most a year out and not within a month", () => {
    const expires = fields("Expires")
    expect(expires).toHaveLength(1)
    const at = Date.parse(expires[0] ?? "")
    expect(Number.isNaN(at)).toBe(false)
    const day = 24 * 60 * 60 * 1000
    expect(at - Date.now()).toBeGreaterThan(30 * day)
    expect(at - Date.now()).toBeLessThanOrEqual(366 * day)
  })

  it("points at itself on the production origin", () => {
    expect(fields("Canonical")).toEqual(["https://equipbible.com/.well-known/security.txt"])
  })
})
