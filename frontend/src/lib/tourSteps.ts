import type { TFunction } from "i18next"
import type { TourStep } from "@/lib/tour"

/**
 * Tour step definitions for the student dashboard.
 *
 * Targets use the ``data-tour`` attribute pattern (not Tailwind class
 * strings or DOM ids) so a routine restyle of the dashboard can't
 * silently break the tour. If a target is missing from the DOM at
 * step-time, driver.js will fall back to a centered popover with no
 * spotlight — degraded but not broken.
 */
export function studentDashboardSteps(t: TFunction): TourStep[] {
  return [
    {
      element: '[data-tour="my-courses"]',
      popover: {
        title: t("tour.student.myCourses.title"),
        description: t("tour.student.myCourses.body"),
        side: "right",
        align: "start",
      },
    },
    {
      element: '[data-tour="verse-of-day"]',
      popover: {
        title: t("tour.student.verse.title"),
        description: t("tour.student.verse.body"),
        side: "left",
        align: "start",
      },
    },
    {
      element: '[data-tour="today"]',
      popover: {
        title: t("tour.student.today.title"),
        description: t("tour.student.today.body"),
        side: "left",
        align: "center",
      },
    },
    {
      element: '[data-tour="streak"]',
      popover: {
        title: t("tour.student.streak.title"),
        description: t("tour.student.streak.body"),
        side: "left",
        align: "end",
      },
    },
    {
      // No element on the closing step — centered popover acts as a
      // graceful "you're done, here's the summary" beat.
      popover: {
        title: t("tour.student.finale.title"),
        description: t("tour.student.finale.body"),
      },
    },
  ]
}

export function teacherDashboardSteps(t: TFunction): TourStep[] {
  return [
    {
      element: '[data-tour="new-course"]',
      popover: {
        title: t("tour.teacher.newCourse.title"),
        description: t("tour.teacher.newCourse.body"),
        side: "bottom",
        align: "end",
      },
    },
    {
      element: '[data-tour="pending-certs"]',
      popover: {
        title: t("tour.teacher.pendingCerts.title"),
        description: t("tour.teacher.pendingCerts.body"),
        side: "bottom",
        align: "center",
      },
    },
    {
      element: '[data-tour="courses-list"]',
      popover: {
        title: t("tour.teacher.coursesList.title"),
        description: t("tour.teacher.coursesList.body"),
        side: "top",
        align: "center",
      },
    },
    {
      popover: {
        title: t("tour.teacher.finale.title"),
        description: t("tour.teacher.finale.body"),
      },
    },
  ]
}
