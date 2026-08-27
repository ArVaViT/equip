import type { UserRole } from "@/types"

/**
 * Single source of truth for mapping a ``UserRole`` enum value (which
 * mirrors Pydantic / Postgres ``CHECK`` constraint) to its i18n key.
 *
 * The bridge lives here so every component that needs to render a role
 * — Profile, Admin dashboard, virtualised admin table, useAdminOverview
 * — uses the same lookup instead of re-deriving it.
 */
export const ROLE_I18N_KEY: Record<UserRole, string> = {
  student: "roles.student",
  teacher: "roles.teacher",
  director: "roles.director",
  admin: "roles.admin",
}

/**
 * Maps each role to its ``<Badge>`` colour variant. Kept next to the
 * i18n map because both are display-time concerns; the same Profile +
 * Admin surfaces use both together.
 */
export const ROLE_BADGE_VARIANT: Record<
  UserRole,
  "destructiveSubtle" | "primarySubtle" | "infoSubtle"
> = {
  // Platform staff read as the strongest colour because their reach is
  // the widest; a director's is the same shape one level in, so it
  // borrows the same variant rather than inventing a fourth.
  admin: "destructiveSubtle",
  director: "destructiveSubtle",
  teacher: "primarySubtle",
  student: "infoSubtle",
}
