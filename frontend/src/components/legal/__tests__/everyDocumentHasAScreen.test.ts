import { readFileSync } from "node:fs"
import { join } from "node:path"
import { describe, expect, it } from "vitest"
import { ROLE_DOCUMENTS } from "../useTeacherAgreement"

/**
 * Every document the server makes somebody sign has a screen that asks for it.
 *
 * The server's consent gate refuses every change from a person who owes a
 * document their role requires. A document nobody's screen asks for is a wall:
 * the School Agreement was one for two months, and the only director on the
 * platform met it as seventeen 403s grading one paper (2026-11-22).
 *
 * The documents everybody signs are asked for by the first-run flow; the
 * role-scoped ones by the agreement gate. This reads the registry the server
 * enforces and fails when a role-scoped document appears that neither asks for.
 */
const REGISTRY = join(__dirname, "..", "..", "..", "..", "..", "backend", "app", "legal", "registry.py")

describe("every document somebody must sign has a screen", () => {
  it("covers each role-scoped document in the registry", () => {
    const source = readFileSync(REGISTRY, "utf8")
    const specs = [...source.matchAll(/slug="([^"]+)",\s*required_for=([A-Za-z_]+(?:\(\))?)/g)].map((m) => ({
      slug: m[1] ?? "",
      requiredFor: m[2] ?? "",
    }))
    expect(specs.length, "the registry could not be read; update this test's pattern").toBeGreaterThan(3)
    // Asked by the first-run flow (everybody signs) or by nobody (notices).
    const askedElsewhere = new Set(["EVERYONE", "frozenset()"])
    const roleScoped = specs.filter((spec) => !askedElsewhere.has(spec.requiredFor)).map((spec) => spec.slug)
    const asked = new Set<string>(ROLE_DOCUMENTS)
    for (const slug of roleScoped) {
      expect(asked.has(slug), `${slug} is required for a role, and no screen asks for it`).toBe(true)
    }
  })
})
