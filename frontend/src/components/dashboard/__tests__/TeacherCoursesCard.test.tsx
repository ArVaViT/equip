import React from "react"
import { render, screen, waitFor } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { I18nextProvider } from "react-i18next"
import { beforeEach, describe, expect, it, vi } from "vitest"

import i18n from "@/i18n/config"
import type { Course } from "@/types"

/**
 * The card on the dashboard that shows a teacher the courses they teach.
 *
 * Contract:
 *   - students never see it;
 *   - a teacher sees their courses by name, each linking into the editor,
 *     plus one link to the teaching section;
 *   - a teacher with no courses is invited to create the first;
 *   - a failed request keeps the card and its link — the one thing it
 *     must never lose.
 */

const auth = vi.hoisted(() => ({ user: { id: "u-1", role: "teacher", full_name: "Пётр" } as
  | { id: string; role: string; full_name: string }
  | null }))

vi.mock("@/context/useAuth", () => ({ useAuth: () => ({ user: auth.user }) }))

// A plain mock function, not `vi.fn()` returning a rejected promise: the
// runner reads `mock.results` and reports that rejection as unhandled
// before the component's `catch` sees it.
const teacherCourses = vi.hoisted(() => ({
  impl: async (): Promise<Course[]> => [],
}))

vi.mock("@/services/courses", () => ({
  coursesService: { getTeacherCourses: () => teacherCourses.impl() },
}))

import { TeacherCoursesCard } from "@/components/dashboard/TeacherCoursesCard"

function Wrapper({ children }: { children: React.ReactNode }) {
  return (
    <I18nextProvider i18n={i18n}>
      <MemoryRouter>{children}</MemoryRouter>
    </I18nextProvider>
  )
}

function makeCourse(over: Partial<Course>): Course {
  return {
    id: "c-1",
    title: "Introduction to Theology",
    description: null,
    image_url: null,
    status: "draft",
    access_mode: "public",
    created_by: "u-1",
    created_at: "2026-09-01T00:00:00Z",
    updated_at: "2026-09-01T00:00:00Z",
    deleted_at: null,
    enrollment_start: null,
    enrollment_end: null,
    ...over,
  }
}

describe("TeacherCoursesCard", () => {
  beforeEach(() => {
    auth.user = { id: "u-1", role: "teacher", full_name: "Пётр" }
    teacherCourses.impl = async () => []
  })

  it("renders nothing for a student", () => {
    auth.user = { id: "s-1", role: "student", full_name: "Мария" }
    render(<TeacherCoursesCard />, { wrapper: Wrapper })
    expect(screen.queryByTestId("teacher-courses-card")).not.toBeInTheDocument()
  })

  it("names the teacher's courses, each linking into its editor", async () => {
    teacherCourses.impl = async () => [
      makeCourse({ id: "c-1", title: "Introduction to Theology", status: "draft" }),
      makeCourse({ id: "c-2", title: "Acts", status: "published" }),
    ]
    render(<TeacherCoursesCard />, { wrapper: Wrapper })
    const first = await screen.findByRole("link", { name: /Introduction to Theology/ })
    expect(first).toHaveAttribute("href", "/teacher/courses/c-1")
    expect(screen.getByRole("link", { name: /Acts/ })).toHaveAttribute("href", "/teacher/courses/c-2")
    expect(screen.getByText("Draft")).toBeInTheDocument()
    expect(screen.getByText("Published")).toBeInTheDocument()
    expect(screen.getByRole("link", { name: /All my courses/ })).toHaveAttribute("href", "/teacher")
  })

  it("shows three and counts the rest", async () => {
    teacherCourses.impl = async () =>
      ["a", "b", "c", "d", "e"].map((id) => makeCourse({ id, title: `Course ${id}` }))
    render(<TeacherCoursesCard />, { wrapper: Wrapper })
    await screen.findByRole("link", { name: /Course a/ })
    expect(screen.getByRole("link", { name: /Course c/ })).toBeInTheDocument()
    expect(screen.queryByRole("link", { name: /Course d/ })).not.toBeInTheDocument()
    expect(screen.getByRole("link", { name: /and 2 more courses/ })).toHaveAttribute("href", "/teacher")
  })

  it("invites a teacher with no courses to create the first", async () => {
    render(<TeacherCoursesCard />, { wrapper: Wrapper })
    expect(await screen.findByText(/You have no courses yet/)).toBeInTheDocument()
    expect(screen.getByRole("link", { name: /Create your first course/ })).toHaveAttribute(
      "href",
      "/teacher",
    )
  })

  it("keeps the card and its link when the request fails", async () => {
    teacherCourses.impl = async () => {
      throw new Error("network")
    }
    render(<TeacherCoursesCard />, { wrapper: Wrapper })
    await waitFor(() => expect(screen.queryByRole("status")).not.toBeInTheDocument())
    expect(screen.getByTestId("teacher-courses-card")).toBeInTheDocument()
    expect(await screen.findByRole("link", { name: /All my courses/ })).toHaveAttribute("href", "/teacher")
    // A failure is not "no courses": the invitation to create one would be a lie.
    expect(screen.queryByText(/You have no courses yet/)).not.toBeInTheDocument()
  })

  it("is shown to an admin too", async () => {
    auth.user = { id: "a-1", role: "admin", full_name: "Admin" }
    render(<TeacherCoursesCard />, { wrapper: Wrapper })
    expect(await screen.findByTestId("teacher-courses-card")).toBeInTheDocument()
  })
})
