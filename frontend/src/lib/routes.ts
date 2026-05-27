/**
 * Single source of truth for every URL path the app routes to.
 *
 * Why: a hardcoded ``<Link to="/teacher">`` scattered across 30+ files
 * means renaming ``/teacher`` → ``/instructor`` becomes a grep-and-replace
 * across the whole frontend, and accidental drift between two near-
 * identical strings (``"/course"`` vs ``"/courses"``) silently 404s in
 * one place while working everywhere else.
 *
 * Convention
 *
 *  - Top-level paths are exported as ``UPPER_CASE`` constants.
 *  - Parametrised paths are exported as builder functions that take
 *    the segment values and return the assembled URL — this catches
 *    typos at compile time, not at runtime.
 *  - The constants live in one flat ``ROUTES`` object so call sites
 *    read as ``ROUTES.TEACHER`` / ``ROUTES.courseDetail(id)`` —
 *    discoverable via IDE autocomplete from any importing file.
 *
 * This file is the *pattern*; routes are migrated as call sites are
 * touched rather than in one mega-grep. New routes added going
 * forward should land here first.
 */

export const ROUTES = {
  // ── Public ────────────────────────────────────────────────────────
  HOME: "/",
  COURSES: "/courses",
  courseDetail: (courseId: string) => `/courses/${courseId}`,
  chapter: (courseId: string, moduleId: string, chapterId: string) =>
    `/courses/${courseId}/modules/${moduleId}/chapters/${chapterId}`,

  // ── Auth ──────────────────────────────────────────────────────────
  LOGIN: "/login",
  REGISTER: "/register",
  FORGOT_PASSWORD: "/forgot-password",
  RESET_PASSWORD: "/auth/reset-password",
  AUTH_CALLBACK: "/auth/callback",
  AUTH_CONFIRM: "/auth/confirm",

  // ── Authenticated student / user ──────────────────────────────────
  DASHBOARD: "/dashboard",
  PROFILE: "/profile",
  CERTIFICATES: "/certificates",
  CALENDAR: "/calendar",

  // ── Teacher ───────────────────────────────────────────────────────
  TEACHER: "/teacher",
  teacherCourseEditor: (courseId: string) => `/teacher/courses/${courseId}`,
  teacherModuleEditor: (courseId: string, moduleId: string) =>
    `/teacher/courses/${courseId}/modules/${moduleId}/edit`,
  teacherChapterEditor: (courseId: string, moduleId: string, chapterId: string) =>
    `/teacher/courses/${courseId}/modules/${moduleId}/chapters/${chapterId}/edit`,
  teacherGradebook: (courseId: string) => `/teacher/courses/${courseId}/gradebook`,
  teacherStudentProgress: (courseId: string) => `/teacher/courses/${courseId}/progress`,
  teacherCourseAnalytics: (courseId: string) => `/teacher/courses/${courseId}/analytics`,

  // ── Admin ─────────────────────────────────────────────────────────
  ADMIN: "/admin",
  ADMIN_COHORTS_TAB: "/admin?tab=cohorts",
} as const
