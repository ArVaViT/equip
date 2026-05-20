import type { TFunction } from "i18next"
import type { TourStep } from "@/lib/tour"

/**
 * Tour step definitions, one factory per surface.
 *
 * Targets use the ``data-tour`` attribute pattern (not Tailwind class
 * strings or DOM ids) so a routine restyle can't silently break the
 * tour. If a target is missing from the DOM at step-time, driver.js
 * falls back to a centered popover with no spotlight — degraded but
 * not broken.
 *
 * Every surface's tour follows the same shape: spotlight steps for
 * the 2–4 most important affordances on the page, then a no-target
 * closing step as a "you're done" beat. Closing-step copy is
 * deliberately reassuring — the moment isn't "tour over, go figure
 * out the rest", it's "you have what you need, go at your own pace".
 */

// ─────────────────────────────────────────────────────────────────────
// Student surfaces
// ─────────────────────────────────────────────────────────────────────

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
      popover: {
        title: t("tour.student.finale.title"),
        description: t("tour.student.finale.body"),
      },
    },
  ]
}

export function coursesCatalogSteps(t: TFunction): TourStep[] {
  return [
    {
      element: '[data-tour="catalog-search"]',
      popover: {
        title: t("tour.catalog.search.title"),
        description: t("tour.catalog.search.body"),
        side: "bottom",
        align: "center",
      },
    },
    {
      element: '[data-tour="catalog-grid"]',
      popover: {
        title: t("tour.catalog.grid.title"),
        description: t("tour.catalog.grid.body"),
        side: "top",
        align: "center",
      },
    },
    {
      popover: {
        title: t("tour.catalog.finale.title"),
        description: t("tour.catalog.finale.body"),
      },
    },
  ]
}

export function courseDetailSteps(t: TFunction): TourStep[] {
  return [
    {
      element: '[data-tour="course-header"]',
      popover: {
        title: t("tour.courseDetail.header.title"),
        description: t("tour.courseDetail.header.body"),
        side: "bottom",
        align: "start",
      },
    },
    {
      element: '[data-tour="module-list"]',
      popover: {
        title: t("tour.courseDetail.modules.title"),
        description: t("tour.courseDetail.modules.body"),
        side: "top",
        align: "center",
      },
    },
    {
      popover: {
        title: t("tour.courseDetail.finale.title"),
        description: t("tour.courseDetail.finale.body"),
      },
    },
  ]
}

export function chapterViewSteps(t: TFunction): TourStep[] {
  return [
    {
      element: '[data-tour="chapter-header"]',
      popover: {
        title: t("tour.chapter.header.title"),
        description: t("tour.chapter.header.body"),
        side: "bottom",
        align: "start",
      },
    },
    {
      element: '[data-tour="chapter-body"]',
      popover: {
        title: t("tour.chapter.body.title"),
        description: t("tour.chapter.body.body"),
        side: "top",
        align: "center",
      },
    },
    {
      element: '[data-tour="chapter-nav"]',
      popover: {
        title: t("tour.chapter.nav.title"),
        description: t("tour.chapter.nav.body"),
        side: "top",
        align: "center",
      },
    },
    {
      popover: {
        title: t("tour.chapter.finale.title"),
        description: t("tour.chapter.finale.body"),
      },
    },
  ]
}

export function certificatesSteps(t: TFunction): TourStep[] {
  return [
    {
      element: '[data-tour="certs-header"]',
      popover: {
        title: t("tour.certs.header.title"),
        description: t("tour.certs.header.body"),
        side: "bottom",
        align: "start",
      },
    },
    {
      popover: {
        title: t("tour.certs.finale.title"),
        description: t("tour.certs.finale.body"),
      },
    },
  ]
}

export function calendarSteps(t: TFunction): TourStep[] {
  return [
    {
      element: '[data-tour="calendar-grid"]',
      popover: {
        title: t("tour.calendar.grid.title"),
        description: t("tour.calendar.grid.body"),
        side: "top",
        align: "center",
      },
    },
    {
      element: '[data-tour="calendar-upcoming"]',
      popover: {
        title: t("tour.calendar.upcoming.title"),
        description: t("tour.calendar.upcoming.body"),
        side: "left",
        align: "start",
      },
    },
    {
      popover: {
        title: t("tour.calendar.finale.title"),
        description: t("tour.calendar.finale.body"),
      },
    },
  ]
}

export function profileSteps(t: TFunction): TourStep[] {
  return [
    {
      element: '[data-tour="profile-form"]',
      popover: {
        title: t("tour.profile.form.title"),
        description: t("tour.profile.form.body"),
        side: "top",
        align: "center",
      },
    },
    {
      popover: {
        title: t("tour.profile.finale.title"),
        description: t("tour.profile.finale.body"),
      },
    },
  ]
}

// ─────────────────────────────────────────────────────────────────────
// Teacher surfaces
// ─────────────────────────────────────────────────────────────────────

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

export function courseEditorSteps(t: TFunction): TourStep[] {
  return [
    {
      element: '[data-tour="course-editor-header"]',
      popover: {
        title: t("tour.courseEditor.header.title"),
        description: t("tour.courseEditor.header.body"),
        side: "bottom",
        align: "start",
      },
    },
    {
      element: '[data-tour="course-editor-tabs"]',
      popover: {
        title: t("tour.courseEditor.tabs.title"),
        description: t("tour.courseEditor.tabs.body"),
        side: "bottom",
        align: "start",
      },
    },
    {
      element: '[data-tour="course-editor-modules"]',
      popover: {
        title: t("tour.courseEditor.modules.title"),
        description: t("tour.courseEditor.modules.body"),
        side: "top",
        align: "center",
      },
    },
    {
      popover: {
        title: t("tour.courseEditor.finale.title"),
        description: t("tour.courseEditor.finale.body"),
      },
    },
  ]
}

export function moduleEditorSteps(t: TFunction): TourStep[] {
  return [
    {
      element: '[data-tour="module-editor-title"]',
      popover: {
        title: t("tour.moduleEditor.title.title"),
        description: t("tour.moduleEditor.title.body"),
        side: "bottom",
        align: "start",
      },
    },
    {
      element: '[data-tour="module-editor-chapters"]',
      popover: {
        title: t("tour.moduleEditor.chapters.title"),
        description: t("tour.moduleEditor.chapters.body"),
        side: "top",
        align: "center",
      },
    },
    {
      popover: {
        title: t("tour.moduleEditor.finale.title"),
        description: t("tour.moduleEditor.finale.body"),
      },
    },
  ]
}

export function chapterEditorSteps(t: TFunction): TourStep[] {
  return [
    {
      element: '[data-tour="chapter-editor-header"]',
      popover: {
        title: t("tour.chapterEditor.header.title"),
        description: t("tour.chapterEditor.header.body"),
        side: "bottom",
        align: "start",
      },
    },
    {
      element: '[data-tour="chapter-editor-blocks"]',
      popover: {
        title: t("tour.chapterEditor.blocks.title"),
        description: t("tour.chapterEditor.blocks.body"),
        side: "top",
        align: "center",
      },
    },
    {
      popover: {
        title: t("tour.chapterEditor.finale.title"),
        description: t("tour.chapterEditor.finale.body"),
      },
    },
  ]
}

export function gradebookSteps(t: TFunction): TourStep[] {
  return [
    {
      element: '[data-tour="gradebook-table"]',
      popover: {
        title: t("tour.gradebook.table.title"),
        description: t("tour.gradebook.table.body"),
        side: "top",
        align: "center",
      },
    },
    {
      popover: {
        title: t("tour.gradebook.finale.title"),
        description: t("tour.gradebook.finale.body"),
      },
    },
  ]
}

export function analyticsSteps(t: TFunction): TourStep[] {
  return [
    {
      element: '[data-tour="analytics-stats"]',
      popover: {
        title: t("tour.analytics.stats.title"),
        description: t("tour.analytics.stats.body"),
        side: "bottom",
        align: "center",
      },
    },
    {
      popover: {
        title: t("tour.analytics.finale.title"),
        description: t("tour.analytics.finale.body"),
      },
    },
  ]
}

export function studentProgressSteps(t: TFunction): TourStep[] {
  return [
    {
      element: '[data-tour="progress-table"]',
      popover: {
        title: t("tour.studentProgress.table.title"),
        description: t("tour.studentProgress.table.body"),
        side: "top",
        align: "center",
      },
    },
    {
      popover: {
        title: t("tour.studentProgress.finale.title"),
        description: t("tour.studentProgress.finale.body"),
      },
    },
  ]
}
