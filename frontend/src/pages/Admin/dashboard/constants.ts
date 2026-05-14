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

/** Background/foreground pair used in audit-log action pills. */
export const ACTION_BADGE_CLASS: Record<string, string> = {
  create: "bg-success/15 text-success",
  update: "bg-info/15 text-info",
  delete: "bg-destructive/15 text-destructive",
  publish: "bg-primary/15 text-primary",
  enroll: "bg-info/15 text-info",
  approve: "bg-success/15 text-success",
  reject: "bg-destructive/15 text-destructive",
  grade: "bg-warning/15 text-warning",
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

/** Role-pill color classes. */
export const ROLE_BADGE_CLASS: Record<UserRole, string> = {
  admin: "bg-destructive/15 text-destructive",
  teacher: "bg-primary/15 text-primary",
  pending_teacher: "bg-warning/15 text-warning",
  student: "bg-info/15 text-info",
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
