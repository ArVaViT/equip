import type { UserRole } from "@/types"

export type AdminTab = "overview" | "cohorts" | "audit"
export const ADMIN_TABS: readonly AdminTab[] = ["overview", "cohorts", "audit"]

export const ACTION_OPTIONS = [
  "create",
  "update",
  "delete",
  "publish",
  "enroll",
  "approve",
  "reject",
  "grade",
] as const

export const RESOURCE_OPTIONS = [
  "course",
  "module",
  "chapter",
  "enrollment",
  "certificate",
  "assignment_submission",
  "user",
] as const

export const ISO_DATE_REGEX = /^\d{4}-\d{2}-\d{2}$/

/** Maps each audit-log action to a `<Badge>` variant. */
export const ACTION_BADGE_VARIANT: Record<
  string,
  | "successSubtle"
  | "infoSubtle"
  | "destructiveSubtle"
  | "primarySubtle"
  | "warningSubtle"
> = {
  create: "successSubtle",
  update: "infoSubtle",
  delete: "destructiveSubtle",
  publish: "primarySubtle",
  enroll: "infoSubtle",
  approve: "successSubtle",
  reject: "destructiveSubtle",
  grade: "warningSubtle",
}

/** Maps each role to its i18n key. Use with ``useTranslation().t`` to
 * render localized role labels — never hardcode the English values.
 *
 * The camelCase keys (``pendingTeacher``) are i18next conventions; the
 * snake_case role values (``pending_teacher``) mirror the Pydantic /
 * Postgres CHECK constraint. The mapping lives here so the bridge is
 * a single source of truth instead of being re-derived in every
 * component that needs to render a role.
 */
export const ROLE_I18N_KEY: Record<UserRole, string> = {
  student: "roles.student",
  pending_teacher: "roles.pendingTeacher",
  teacher: "roles.teacher",
  admin: "roles.admin",
}

/** Maps each role to its `<Badge>` variant. */
export const ROLE_BADGE_VARIANT: Record<
  UserRole,
  "destructiveSubtle" | "primarySubtle" | "warningSubtle" | "infoSubtle"
> = {
  admin: "destructiveSubtle",
  teacher: "primarySubtle",
  pending_teacher: "warningSubtle",
  student: "infoSubtle",
}

export interface ProfileRow {
  id: string
  email: string
  full_name: string | null
  role: UserRole
  created_at: string
  avatar_url: string | null
}

export interface AdminStats {
  users: number
  courses: number
  enrollments: number
}
