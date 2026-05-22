import type { UserRole } from "@/types"

/**
 * Single source of truth for mapping a ``UserRole`` enum value (which
 * mirrors Pydantic / Postgres ``CHECK`` constraint) to its i18n key.
 *
 * The camelCase keys (``pendingTeacher``) are i18next conventions; the
 * snake_case role values (``pending_teacher``) mirror the API contract.
 * The bridge lives here so every component that needs to render a role
 * — Profile, Admin dashboard, virtualised admin table, useAdminOverview
 * — uses the same lookup instead of re-deriving it.
 */
export const ROLE_I18N_KEY: Record<UserRole, string> = {
  student: "roles.student",
  pending_teacher: "roles.pendingTeacher",
  teacher: "roles.teacher",
  admin: "roles.admin",
}

/**
 * Maps each role to its ``<Badge>`` colour variant. Kept next to the
 * i18n map because both are display-time concerns; the same Profile +
 * Admin surfaces use both together.
 */
export const ROLE_BADGE_VARIANT: Record<
  UserRole,
  "destructiveSubtle" | "primarySubtle" | "warningSubtle" | "infoSubtle"
> = {
  admin: "destructiveSubtle",
  teacher: "primarySubtle",
  pending_teacher: "warningSubtle",
  student: "infoSubtle",
}
