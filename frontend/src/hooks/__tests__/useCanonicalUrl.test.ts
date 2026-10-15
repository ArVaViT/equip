import { describe, expect, it } from "vitest"

import { CANONICAL_STATIC_PATHS, canonicalUrlFor } from "../useCanonicalUrl"
// @ts-expect-error — plain ESM build script, no type declarations by design.
import { STATIC_PAGES } from "../../../scripts/build-sitemap.mjs"

describe("canonicalUrlFor", () => {
  it("names the same static pages the sitemap lists", () => {
    expect([...CANONICAL_STATIC_PATHS].sort()).toEqual(
      (STATIC_PAGES as Array<{ path: string }>).map((p) => p.path).sort(),
    )
  })

  it("gives each public page its own address", () => {
    expect(canonicalUrlFor("/")).toBe("https://equipbible.com/")
    expect(canonicalUrlFor("/verify/")).toBe("https://equipbible.com/verify")
    expect(canonicalUrlFor("/courses/B8D24482-F630-49DC-990A-72DDB0717DE0")).toBe(
      "https://equipbible.com/courses/b8d24482-f630-49dc-990a-72ddb0717de0",
    )
    expect(canonicalUrlFor("/o/ucoat")).toBe("https://equipbible.com/o/ucoat")
  })

  it("gives none to pages that are not documents of their own", () => {
    for (const path of ["/login", "/profile", "/courses/not-a-uuid", "/verify/EQ-123", "/nowhere"]) {
      expect(canonicalUrlFor(path), path).toBeNull()
    }
  })
})
