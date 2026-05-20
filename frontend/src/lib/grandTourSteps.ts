import type { TFunction } from "i18next"
import type { GrandTourStep } from "@/lib/grandTour"

/**
 * Student grand tour — the first-time guided walkthrough that auto-
 * navigates across the top-level student routes:
 *
 *   /  →  /courses  →  /calendar  →  /certificates  →  /profile  →  /
 *
 * Each step targets the same ``data-tour="…"`` anchors the per-page
 * tours use, so spotlights land on the exact same elements; the
 * orchestrator just chains them across routes.
 *
 * **Why student-only**: the teacher journey requires a course id for
 * the editor surfaces (``/teacher/courses/:id``) which a brand-new
 * teacher with zero courses doesn't have. Per-page tours still fire
 * on each teacher surface the first time the teacher reaches it, so
 * teachers don't lose the guided experience — they just don't get
 * the auto-piloted walk.
 */
export function studentGrandTourSteps(t: TFunction): GrandTourStep[] {
  return [
    // ─────── Dashboard ─────────────────────────────────────────────
    {
      route: "/",
      element: '[data-tour="my-courses"]',
      popover: {
        title: t("grandTour.welcome.title"),
        description: t("grandTour.welcome.body"),
        side: "right",
        align: "start",
      },
    },
    {
      route: "/",
      element: '[data-tour="verse-of-day"]',
      popover: {
        title: t("tour.student.verse.title"),
        description: t("tour.student.verse.body"),
        side: "left",
        align: "start",
      },
    },
    {
      route: "/",
      element: '[data-tour="today"]',
      popover: {
        title: t("tour.student.today.title"),
        description: t("tour.student.today.body"),
        side: "left",
        align: "center",
      },
    },
    {
      route: "/",
      element: '[data-tour="streak"]',
      popover: {
        title: t("tour.student.streak.title"),
        description: t("tour.student.streak.body"),
        side: "left",
        align: "end",
      },
    },
    // ─────── Catalog ───────────────────────────────────────────────
    {
      route: "/courses",
      element: '[data-tour="catalog-search"]',
      popover: {
        title: t("tour.catalog.search.title"),
        description: t("tour.catalog.search.body"),
        side: "bottom",
        align: "center",
      },
    },
    {
      route: "/courses",
      element: '[data-tour="catalog-grid"]',
      popover: {
        title: t("tour.catalog.grid.title"),
        description: t("tour.catalog.grid.body"),
        side: "top",
        align: "center",
      },
    },
    // ─────── Calendar ──────────────────────────────────────────────
    // The grid + upcoming panel only render once the user has at
    // least one enrollment; a brand-new user without any will see an
    // EmptyState here. The tour step still highlights the page-level
    // header in that case (the eyebrow + title) via the centered
    // fallback when the data-tour anchor is missing.
    {
      route: "/calendar",
      element: '[data-tour="calendar-grid"]',
      popover: {
        title: t("grandTour.calendar.title"),
        description: t("grandTour.calendar.body"),
        side: "top",
        align: "center",
      },
    },
    // ─────── Certificates ──────────────────────────────────────────
    {
      route: "/certificates",
      element: '[data-tour="certs-header"]',
      popover: {
        title: t("tour.certs.header.title"),
        description: t("tour.certs.header.body"),
        side: "bottom",
        align: "start",
      },
    },
    // ─────── Profile ───────────────────────────────────────────────
    {
      route: "/profile",
      element: '[data-tour="profile-form"]',
      popover: {
        title: t("tour.profile.form.title"),
        description: t("tour.profile.form.body"),
        side: "top",
        align: "center",
      },
    },
    // ─────── Finale (back home) ────────────────────────────────────
    {
      route: "/",
      popover: {
        title: t("grandTour.finale.title"),
        description: t("grandTour.finale.body"),
      },
    },
  ]
}

/**
 * Identifiers of per-page tours that the grand tour covers. When the
 * grand tour completes (or is dismissed), the hook writes ``seen``
 * flags for each of these so the user doesn't immediately get a
 * second wave of per-page tours on revisit.
 *
 * Per-page tours NOT in this list (chapter view, course detail,
 * course editor, chapter editor, etc.) still fire on first visit —
 * those are deep contextual surfaces the grand tour deliberately
 * skips, and a contextual tour the first time you land on them is
 * still desirable.
 */
export const STUDENT_GRAND_TOUR_COVERS = [
  "student-dashboard-v1",
  "courses-catalog-v1",
  "calendar-v1",
  "certificates-v1",
  "profile-v1",
] as const
