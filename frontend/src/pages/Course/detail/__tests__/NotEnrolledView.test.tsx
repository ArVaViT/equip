import React from "react"
import { render, screen } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { I18nextProvider } from "react-i18next"
import { describe, expect, it } from "vitest"

import i18n from "@/i18n/config"
import type { Course } from "@/types"
import { NotEnrolledView } from "@/pages/Course/detail/NotEnrolledView"

/**
 * The course page for somebody who is not enrolled — and, in particular,
 * for the author of a course nobody can enroll in yet.
 *
 * Before: the owner of a draft saw the same "Enroll" button as everyone
 * else, and pressing it ended in "this course is not published yet". The
 * server hands the owner the draft's modules and chapters; the page threw
 * them away. Now the owner of an unpublished course gets the outline with
 * a link into every chapter, and no button that cannot work.
 */

function Wrapper({ children }: { children: React.ReactNode }) {
  return (
    <I18nextProvider i18n={i18n}>
      <MemoryRouter>{children}</MemoryRouter>
    </I18nextProvider>
  )
}

function makeCourse(over: Partial<Course> = {}): Course {
  return {
    id: "c-1",
    title: "Acts of the Apostles",
    description: "Six questions.",
    image_url: null,
    status: "draft",
    access_mode: "public",
    created_by: "t-1",
    created_at: "2026-09-01T00:00:00Z",
    updated_at: "2026-09-01T00:00:00Z",
    deleted_at: null,
    enrollment_start: null,
    enrollment_end: null,
    modules: [
      {
        id: "m-2",
        course_id: "c-1",
        title: "Second module",
        description: null,
        order_index: 1,
        due_date: null,
        chapters: [],
      },
      {
        id: "m-1",
        course_id: "c-1",
        title: "First module",
        description: null,
        order_index: 0,
        due_date: null,
        chapters: [
          {
            id: "ch-2",
            module_id: "m-1",
            title: "Quiz on Pentecost",
            order_index: 1,
            chapter_type: "quiz",
            requires_completion: true,
            is_locked: true,
          },
          {
            id: "ch-1",
            module_id: "m-1",
            title: "Pentecost",
            order_index: 0,
            chapter_type: "reading",
            requires_completion: false,
            is_locked: false,
          },
        ],
      },
    ],
    ...over,
  }
}

function renderView(course: Course, isOwner: boolean) {
  return render(
    <NotEnrolledView
      course={course}
      cohorts={[]}
      isOwner={isOwner}
      isSignedIn
      enrolling={false}
      onEnroll={() => {}}
    />,
    { wrapper: Wrapper },
  )
}

describe("NotEnrolledView — the author on an unpublished course", () => {
  it("shows the outline with a link into every chapter instead of an Enroll button", () => {
    renderView(makeCourse({ status: "draft" }), true)
    expect(screen.queryByRole("button", { name: /Enroll in Course/i })).not.toBeInTheDocument()
    expect(screen.getByTestId("owner-preview")).toBeInTheDocument()

    const outline = screen.getByTestId("draft-outline")
    expect(outline).toBeInTheDocument()
    // The link's name carries the chapter type after the title ("Pentecost Reading").
    expect(screen.getByRole("link", { name: /^Pentecost/ })).toHaveAttribute(
      "href",
      "/courses/c-1/modules/m-1/chapters/ch-1",
    )
    expect(screen.getByRole("link", { name: /Quiz on Pentecost/ })).toHaveAttribute(
      "href",
      "/courses/c-1/modules/m-1/chapters/ch-2",
    )
    expect(screen.getByRole("link", { name: "First module" })).toHaveAttribute(
      "href",
      "/courses/c-1/modules/m-1",
    )
    // A module with no chapters says so rather than rendering an empty box.
    expect(screen.getByText(/This module has no chapters yet/)).toBeInTheDocument()
  })

  it("orders modules and chapters by their index, not by arrival", () => {
    renderView(makeCourse({ status: "draft" }), true)
    const outline = screen.getByTestId("draft-outline")
    const text = outline.textContent ?? ""
    expect(text.indexOf("First module")).toBeLessThan(text.indexOf("Second module"))
    expect(text.indexOf("Pentecost")).toBeLessThan(text.indexOf("Quiz on Pentecost"))
  })

  it("explains that nobody can enroll yet and leads back to the editor", () => {
    renderView(makeCourse({ status: "publishing" }), true)
    expect(screen.getByText(/Until then nobody can enroll/)).toBeInTheDocument()
    expect(screen.getByRole("link", { name: /Back to the course editor/ })).toHaveAttribute(
      "href",
      "/teacher/courses/c-1",
    )
    expect(screen.getByRole("link", { name: /Manage Course/i })).toHaveAttribute(
      "href",
      "/teacher/courses/c-1",
    )
  })

  it("keeps the ordinary owner view — Manage plus Enroll — once the course is published", () => {
    renderView(makeCourse({ status: "published" }), true)
    expect(screen.queryByTestId("owner-preview")).not.toBeInTheDocument()
    expect(screen.queryByTestId("draft-outline")).not.toBeInTheDocument()
    expect(screen.getByRole("button", { name: /Enroll in Course/i })).toBeInTheDocument()
    expect(screen.getByRole("link", { name: /Manage Course/i })).toBeInTheDocument()
  })

  it("never shows a student the draft outline", () => {
    renderView(makeCourse({ status: "draft" }), false)
    expect(screen.queryByTestId("draft-outline")).not.toBeInTheDocument()
    expect(screen.getByRole("button", { name: /Enroll in Course/i })).toBeInTheDocument()
  })
})
