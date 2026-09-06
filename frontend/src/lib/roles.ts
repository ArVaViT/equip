import { ROLES, type UserRole } from "@/types"

/**
 * The roles that author and run courses: a teacher, a director, platform
 * staff. A director is an organization's administrator *and* very often
 * the one teaching in it — a school small enough to have one director
 * rarely has a separate faculty — so the teaching surface is open to both.
 *
 * This is the single definition. The route gate, the header, the
 * dashboard card and every "am I a teacher?" branch call ``canTeach``
 * rather than comparing ``role`` to ``"teacher"`` by hand; the backend's
 * ``TEACHING_ROLES`` in ``app/models/user.py`` mirrors it exactly.
 *
 * What this does NOT grant: ownership. Whether a director may edit *this*
 * course is still ``created_by``, exactly as it is for a teacher.
 */
export const TEACHING_ROLES: ReadonlySet<UserRole> = new Set<UserRole>([
  ROLES.ADMIN,
  ROLES.DIRECTOR,
  ROLES.TEACHER,
])

export function canTeach(role: UserRole | null | undefined): boolean {
  return role != null && TEACHING_ROLES.has(role)
}

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
