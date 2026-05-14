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

/** Human-readable role names for dropdowns and badges. */
export const ROLE_DISPLAY_NAMES: Record<UserRole, string> = {
  student: "Student",
  pending_teacher: "Pending Teacher",
  teacher: "Teacher",
  admin: "Admin",
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
