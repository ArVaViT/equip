import type { UserRole } from "@/types"

// Re-export from the shared location so Profile + other surfaces can
// use the same role i18n mapping without depending on Admin pages.
export { ROLE_I18N_KEY, ROLE_BADGE_VARIANT } from "@/lib/roles"

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
