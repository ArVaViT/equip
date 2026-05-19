import type { UserRole } from "@/types"

// Re-export from the shared location so Admin pages don't have to
// reach into ``@/lib/roles`` directly for the i18n mapping.
export { ROLE_I18N_KEY } from "@/lib/roles"

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
  /** Users created in the last 7 days. Computed client-side from the
   *  full ``users`` list (already loaded for the Users tab), so no
   *  extra API hit. ``undefined`` while loading; concrete number once
   *  the overview fetch resolves. */
  usersLast7Days?: number
}
