import { describe, expect, it } from "vitest"

import { ROLE_BADGE_VARIANT, ROLE_I18N_KEY, TEACHING_ROLES, canTeach } from "@/lib/roles"

/**
 * ``lib/roles.ts`` is the single source of truth that maps a
 * ``UserRole`` enum value (which mirrors the Pydantic Literal /
 * Postgres CHECK constraint on ``profiles.role``) to its i18n key and
 * its Badge variant. The Profile, Admin dashboard, virtualised admin
 * table, and ``useAdminOverview`` all read these maps — so a
 * mismatch silently de-syncs the entire role-display surface.
 *
 * Tests:
 *   1. Every backend role has an i18n key.
 *   2. The i18n keys live under the ``roles.*`` namespace (matches
 *      ``i18n/locales/{en,ru}.json``).
 *   3. Every backend role has a Badge variant.
 *   4. Variant assignments match the design contract: admin =
 *      destructive (most authority), teacher = primary, student = info
 *      (default state).
 *
 * If a new role lands in ``UserRole`` and these maps don't get
 * updated, TypeScript will reject the missing key in the
 * ``Record<UserRole, …>`` type — these runtime tests catch the
 * complementary case where the *value* is wrong.
 */

const ALL_ROLES = ["student", "teacher", "director", "admin"] as const

describe("ROLE_I18N_KEY", () => {
  it("covers every UserRole", () => {
    for (const r of ALL_ROLES) {
      expect(ROLE_I18N_KEY[r]).toBeDefined()
    }
  })

  it("keys all live under the roles.* namespace", () => {
    for (const r of ALL_ROLES) {
      expect(ROLE_I18N_KEY[r].startsWith("roles.")).toBe(true)
    }
  })

  it("locks in the exact mapping (regression guard against silent rename)", () => {
    expect(ROLE_I18N_KEY).toEqual({
      student: "roles.student",
      teacher: "roles.teacher",
      director: "roles.director",
      admin: "roles.admin",
    })
  })
})

describe("ROLE_BADGE_VARIANT", () => {
  it("covers every UserRole", () => {
    for (const r of ALL_ROLES) {
      expect(ROLE_BADGE_VARIANT[r]).toBeDefined()
    }
  })

  it("matches the design contract for tone-by-authority", () => {
    // Admin should read as "most authority / destructive-tone weight"
    expect(ROLE_BADGE_VARIANT.admin).toBe("destructiveSubtle")
    // A director's reach is the admin's shape one level in — inside one
    // organization rather than across the platform — so it reads in the
    // same tone rather than inventing a fourth colour.
    expect(ROLE_BADGE_VARIANT.director).toBe("destructiveSubtle")
    // Teacher is the platform's primary brand role
    expect(ROLE_BADGE_VARIANT.teacher).toBe("primarySubtle")
    // Student is the default state → info tone
    expect(ROLE_BADGE_VARIANT.student).toBe("infoSubtle")
  })

  it("every variant uses the *Subtle suffix (matches the Badge design tier)", () => {
    for (const r of ALL_ROLES) {
      expect(ROLE_BADGE_VARIANT[r]).toMatch(/Subtle$/)
    }
  })
})

describe("canTeach", () => {
  /**
   * The one predicate behind the teacher route gate, the "Преподавание"
   * header item and the dashboard's "my courses" card. On 6 September
   * 2026 the first real teacher — a school director — was bounced off
   * every one of them because each compared the role to "teacher" by
   * hand. A director runs the school and teaches in it; the surface is
   * theirs. Ownership of a given course is decided elsewhere.
   */
  it("admits a teacher, a director and platform staff", () => {
    expect(canTeach("teacher")).toBe(true)
    expect(canTeach("director")).toBe(true)
    expect(canTeach("admin")).toBe(true)
  })

  it("refuses a student and an absent role", () => {
    expect(canTeach("student")).toBe(false)
    expect(canTeach(null)).toBe(false)
    expect(canTeach(undefined)).toBe(false)
  })

  it("is defined once, and matches the backend's TEACHING_ROLES", () => {
    expect([...TEACHING_ROLES].sort()).toEqual(["admin", "director", "teacher"])
  })
})
