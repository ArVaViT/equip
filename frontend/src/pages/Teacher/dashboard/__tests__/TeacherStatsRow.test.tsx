import type { ReactNode } from "react"
import { render, screen } from "@testing-library/react"
import { I18nextProvider } from "react-i18next"
import { describe, expect, it } from "vitest"
import i18n from "@/i18n/config"
import { axe } from "@/test/a11y"
import { TeacherStatsRow } from "../TeacherStatsRow"
import type { Course } from "@/types"

function makeCourse(overrides: Partial<Course> = {}): Course {
  return {
    id: "c-1",
    title: "Test Course",
    description: null,
    image_url: null,
    status: "published",
    access_mode: "public",
    created_by: "teacher-1",
    created_at: "2025-01-01T00:00:00Z",
    updated_at: "2025-01-01T00:00:00Z",
    deleted_at: null,
    enrollment_start: null,
    enrollment_end: null,
    modules: [],
    ...overrides,
  }
}

function TestWrapper({ children }: { children: ReactNode }) {
  return <I18nextProvider i18n={i18n}>{children}</I18nextProvider>
}

describe("TeacherStatsRow", () => {
  it("counts total courses, published courses, and modules", () => {
    const courses = [
      makeCourse({ id: "c-1", status: "published", modules: [{ id: "m1", course_id: "c-1", title: "A", description: null, order_index: 0, due_date: null }] }),
      makeCourse({ id: "c-2", status: "draft", modules: [] }),
      makeCourse({
        id: "c-3",
        status: "published",
        modules: [
          { id: "m2", course_id: "c-3", title: "B", description: null, order_index: 0, due_date: null },
          { id: "m3", course_id: "c-3", title: "C", description: null, order_index: 1, due_date: null },
          { id: "m4", course_id: "c-3", title: "D", description: null, order_index: 2, due_date: null },
        ],
      }),
    ]
    render(<TeacherStatsRow courses={courses} pendingActions={5} />, { wrapper: TestWrapper })

    // total courses = 3, published = 2, modules = 1 + 0 + 3 = 4, pending = 5 — four distinct values.
    expect(screen.getByText("3")).toBeInTheDocument()
    expect(screen.getByText("2")).toBeInTheDocument()
    expect(screen.getByText("4")).toBeInTheDocument()
    expect(screen.getByText("5")).toBeInTheDocument()
  })

  it("shows zero counts (not hidden) when courses have no modules and nothing is pending", () => {
    render(<TeacherStatsRow courses={[makeCourse()]} pendingActions={0} />, { wrapper: TestWrapper })
    // "Modules" and "Needs attention" both read 0 — zeros still render
    expect(screen.getAllByText("0").length).toBeGreaterThanOrEqual(2)
  })

  it("renders without a11y violations", async () => {
    const { container } = render(
      <TeacherStatsRow courses={[makeCourse()]} pendingActions={1} />,
      { wrapper: TestWrapper },
    )
    expect(await axe(container)).toHaveNoViolations()
  })
})
