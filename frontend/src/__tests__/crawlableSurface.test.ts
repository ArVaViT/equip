import { readFileSync } from "node:fs"
import { join } from "node:path"
import { describe, expect, it } from "vitest"

/**
 * Every public route is either offered to crawlers or withheld from them —
 * never neither by accident.
 *
 * The sitemap is hand-written, and /verify — added the same week — was not in
 * it. That page is the only one on the site meant for a stranger: every
 * certificate prints a number that points there, and the person checking it
 * is not a user of this site and never will be. It was the one page that
 * needed to be findable, and it was the one page missing.
 *
 * Four more (the auth landings and the invite acceptance) were absent from
 * both files — not indexed by luck rather than by decision. They carry
 * one-time tokens in the URL, so they belong in robots.txt, and now say so.
 *
 * Routes are read out of App.tsx so this cannot drift the way the sitemap
 * did. A new public route fails here until somebody decides which of the two
 * it belongs in.
 */

const ROOT = join(__dirname, "..", "..")
const APP = readFileSync(join(ROOT, "src", "App.tsx"), "utf8")
const SITEMAP = readFileSync(join(ROOT, "public", "sitemap.xml"), "utf8")
const ROBOTS = readFileSync(join(ROOT, "public", "robots.txt"), "utf8")

/** Static routes no auth gate stands in front of. */
function publicStaticRoutes(): string[] {
  return [...APP.matchAll(/<Route\s+path="([^"]+)"\s+element=\{([^\n]*)/g)]
    .map((match) => ({ path: match[1]!, element: match[2]! }))
    .filter(({ path }) => !path.includes(":") && path !== "*")
    .filter(({ element }) => !/mode="(private|teacher|admin)"/.test(element))
    .map(({ path }) => path)
}

const disallowed = ROBOTS.split("\n")
  .filter((line) => line.startsWith("Disallow:"))
  .map((line) => line.slice("Disallow:".length).trim())
  .filter(Boolean)

describe("the crawlable surface", () => {
  it("accounts for every public route", () => {
    const unaccounted = publicStaticRoutes().filter((path) => {
      const listed = SITEMAP.includes(`https://equipbible.com${path}<`)
      const blocked = disallowed.some((prefix) => path.startsWith(prefix))
      return !listed && !blocked
    })

    expect(
      unaccounted,
      `Neither in sitemap.xml nor disallowed in robots.txt — decide which:\n  ${unaccounted.join("\n  ")}`,
    ).toEqual([])
  })

  it("offers the certificate check to crawlers", () => {
    // Named on its own because it is the reason the rule above exists.
    expect(SITEMAP).toContain("https://equipbible.com/verify<")
    expect(disallowed.some((prefix) => "/verify".startsWith(prefix))).toBe(false)
  })

  it("keeps token-carrying links out of the index", () => {
    for (const path of ["/auth/confirm", "/auth/reset-password", "/invite/accept"]) {
      expect(
        disallowed.some((prefix) => path.startsWith(prefix)),
        `${path} carries a one-time token and must be disallowed`,
      ).toBe(true)
    }
  })
})
