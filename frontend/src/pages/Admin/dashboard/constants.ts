import type { UserRole } from "@/types"

// Re-export from the shared location so Admin pages don't have to
// reach into ``@/lib/roles`` directly for the i18n mapping.
export { ROLE_I18N_KEY } from "@/lib/roles"

export type AdminTab = "overview" | "cohorts" | "audit"
export const ADMIN_TABS: readonly AdminTab[] = ["overview", "cohorts", "audit"]

/** Stable DOM ids for each admin tab's trigger button. Mirrors of these
 *  live on the corresponding ``role="tabpanel"`` wrappers in
 *  ``AdminDashboard.tsx`` via ``aria-labelledby``, so screen readers
 *  hear "Cohorts, tab, selected" and the panel reads as belonging to
 *  that tab. Kept in the constants module so AdminTabs.tsx stays a
 *  pure component file (no shared constants → no Fast Refresh
 *  invalidation when only the component changes). */
export const ADMIN_TAB_TRIGGER_ID = {
  overview: "admin-tab-overview",
  cohorts: "admin-tab-cohorts",
  audit: "admin-tab-audit",
} as const

export const ADMIN_TAB_PANEL_ID = {
  overview: "admin-tabpanel-overview",
  cohorts: "admin-tabpanel-cohorts",
  audit: "admin-tabpanel-audit",
} as const

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

// Static i18n key lookups — callers use ``t(ACTION_LABEL_KEYS[o])``
// instead of ``t(`admin.audit.actionValue.${o}`)`` so the keyCoverage
// test can see each literal at scan time. Per docs/I18N.md.
export const ACTION_LABEL_KEYS: Record<(typeof ACTION_OPTIONS)[number], string> = {
  create: "admin.audit.actionValue.create",
  update: "admin.audit.actionValue.update",
  delete: "admin.audit.actionValue.delete",
  publish: "admin.audit.actionValue.publish",
  enroll: "admin.audit.actionValue.enroll",
  approve: "admin.audit.actionValue.approve",
  reject: "admin.audit.actionValue.reject",
  grade: "admin.audit.actionValue.grade",
}

export const RESOURCE_LABEL_KEYS: Record<(typeof RESOURCE_OPTIONS)[number], string> = {
  course: "admin.audit.resourceValue.course",
  module: "admin.audit.resourceValue.module",
  chapter: "admin.audit.resourceValue.chapter",
  enrollment: "admin.audit.resourceValue.enrollment",
  certificate: "admin.audit.resourceValue.certificate",
  assignment_submission: "admin.audit.resourceValue.assignment_submission",
  user: "admin.audit.resourceValue.user",
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
