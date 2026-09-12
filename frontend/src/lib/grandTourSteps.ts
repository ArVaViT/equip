import type { TFunction } from "i18next"
import type { GrandTourStep } from "@/lib/grandTour"

/**
 * Student grand tour — the first-time walkthrough, and it stays on the
 * dashboard.
 *
 * It used to walk the whole product: dashboard → catalogue → calendar
 * → certificates → profile, twelve steps, auto-navigating between
 * routes. Somebody arriving through an invitation wants to open the
 * course they were invited to, and a twelve-step tour of surfaces they
 * have not asked about yet stands between them and it.
 *
 * Nothing is lost by shortening it: the catalogue, calendar,
 * certificates and profile each have their own per-page tour, which
 * fires the first time a person actually goes there — where it is
 * about something in front of them rather than somewhere they have
 * been teleported. That is also why they came off
 * ``STUDENT_GRAND_TOUR_COVERS`` below: staying on that list would mark
 * them seen and silence the explanation entirely.
 *
 * Each step targets the same ``data-tour="…"`` anchors the per-page
 * tours use, so spotlights land on the exact same elements.
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
      element: '[data-tour="daily-challenge"]',
      popover: {
        title: t("tour.student.streak.title"),
        description: t("tour.student.streak.body"),
        side: "left",
        align: "end",
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
export const STUDENT_GRAND_TOUR_COVERS = ["student-dashboard-v1"] as const
