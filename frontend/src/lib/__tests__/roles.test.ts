import { describe, expect, it } from "vitest"

import { ROLE_BADGE_VARIANT, ROLE_I18N_KEY } from "@/lib/roles"

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
 *      destructive (most authority), teacher = primary, pending =
 *      warning (action needed), student = info (default state).
 *
 * If a new role lands in ``UserRole`` and these maps don't get
 * updated, TypeScript will reject the missing key in the
 * ``Record<UserRole, …>`` type — these runtime tests catch the
 * complementary case where the *value* is wrong.
 */

const ALL_ROLES = ["student", "pending_teacher", "teacher", "admin"] as const

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

  it("uses camelCase for the i18n suffix (matches i18next conventions)", () => {
    // snake_case role value → camelCase i18n suffix
    expect(ROLE_I18N_KEY.pending_teacher).toBe("roles.pendingTeacher")
  })

  it("locks in the exact mapping (regression guard against silent rename)", () => {
    expect(ROLE_I18N_KEY).toEqual({
      student: "roles.student",
      pending_teacher: "roles.pendingTeacher",
      teacher: "roles.teacher",
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
    // Teacher is the platform's primary brand role
    expect(ROLE_BADGE_VARIANT.teacher).toBe("primarySubtle")
    // Pending teacher needs admin attention → warning tone
    expect(ROLE_BADGE_VARIANT.pending_teacher).toBe("warningSubtle")
    // Student is the default state → info tone
    expect(ROLE_BADGE_VARIANT.student).toBe("infoSubtle")
  })

  it("every variant uses the *Subtle suffix (matches the Badge design tier)", () => {
    for (const r of ALL_ROLES) {
      expect(ROLE_BADGE_VARIANT[r]).toMatch(/Subtle$/)
    }
  })
})
