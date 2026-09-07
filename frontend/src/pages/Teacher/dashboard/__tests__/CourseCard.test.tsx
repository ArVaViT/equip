import type { ReactNode } from "react"
import { render, screen } from "@testing-library/react"
import { I18nextProvider } from "react-i18next"
import { MemoryRouter } from "react-router-dom"
import { describe, expect, it, vi } from "vitest"
import i18n from "@/i18n/config"
import { CourseCard } from "../CourseCard"
import type { Course } from "@/types"

function makeCourse(overrides: Partial<Course> = {}): Course {
  return {
    id: "c-1",
    title: "Послание к Римлянам",
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

function Wrapper({ children }: { children: ReactNode }) {
  return (
    <I18nextProvider i18n={i18n}>
      <MemoryRouter>{children}</MemoryRouter>
    </I18nextProvider>
  )
}

function renderCard(pendingGrading?: number, course: Course = makeCourse()) {
  return render(
    <CourseCard
      course={course}
      pendingGrading={pendingGrading}
      togglingId={null}
      cloningId={null}
      onToggleStatus={vi.fn()}
      onClone={vi.fn()}
      onDelete={vi.fn()}
    />,
    { wrapper: Wrapper },
  )
}

describe("CourseCard — work waiting on the teacher", () => {
  it("says how much is waiting and links straight to the gradebook", async () => {
    await i18n.changeLanguage("ru")
    renderCard(3)

    // The header count answers "do I owe anyone anything today". This answers
    // "where" — without the link the teacher still has to hunt for the course.
    const link = screen.getByRole("link", { name: /на проверку/i })
    expect(link).toHaveAttribute("href", "/teacher/courses/c-1/gradebook")
  })

  it("says nothing when nothing is waiting", async () => {
    await i18n.changeLanguage("ru")
    renderCard(0)

    // A badge that is always there stops being a signal. The dashboard-level
    // zero is worth stating; a per-course zero on every card is noise.
    expect(screen.queryByText(/на проверку/i)).not.toBeInTheDocument()
  })

  it("says nothing when the count was never loaded", async () => {
    await i18n.changeLanguage("ru")
    renderCard(undefined)

    // The rollup request is allowed to fail without taking the dashboard with
    // it — in that case the card must not claim zero work is waiting.
    expect(screen.queryByText(/на проверку/i)).not.toBeInTheDocument()
  })
})

describe("CourseCard — a course that is out but not in the catalog yet", () => {
  // The server answers the first publish of an untranslated course with
  // ``publishing``: the teacher did publish it, but nobody can see it
  // until every language has it. "Draft" would be a lie, "Published" a
  // worse one — and offering "Publish" again would tell the teacher
  // their click did not count.
  it("wears its own badge and offers to take the course back, not to publish it again", async () => {
    await i18n.changeLanguage("ru")
    renderCard(0, makeCourse({ status: "publishing" }))

    expect(screen.getByText("Публикуется")).toBeInTheDocument()
    expect(screen.queryByText("Черновик")).not.toBeInTheDocument()
    expect(screen.queryByText("Опубликован")).not.toBeInTheDocument()

    expect(screen.getAllByTitle("Снять с публикации").length).toBeGreaterThan(0)
    expect(screen.queryByTitle("Опубликовать")).not.toBeInTheDocument()
  })
})
