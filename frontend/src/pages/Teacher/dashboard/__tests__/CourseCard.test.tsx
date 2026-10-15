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

describe("CourseCard — how much of the course is written", () => {
  // The card used to show one number, ``modules.length``. For a course that
  // is four finished lessons and no grouping that reads "0 модулей" — true,
  // and a lie about an empty course. The counts come from the server, which
  // is what makes them right on a list payload carrying no chapter rows.
  it("counts lessons, and says nothing about modules when there are none", async () => {
    await i18n.changeLanguage("ru")
    renderCard(0, makeCourse({ chapter_count: 4, module_count: 0 }))

    expect(screen.getByText("4 урока")).toBeInTheDocument()
    expect(screen.queryByText(/(?<!\p{L})модул\p{L}*/iu)).not.toBeInTheDocument()
  })

  it("adds the module count for a course that groups its lessons", async () => {
    await i18n.changeLanguage("ru")
    renderCard(0, makeCourse({ chapter_count: 7, module_count: 2 }))

    expect(screen.getByText("7 уроков")).toBeInTheDocument()
    expect(screen.getByText("2 модуля")).toBeInTheDocument()
  })

  it("opens the course from its name, and from nowhere else twice", async () => {
    renderCard()
    const course = makeCourse()
    const name = await screen.findByRole("link", { name: course.title })
    expect(name).toHaveAttribute("href", `/teacher/courses/${course.id}`)
    // The pencil went the same way the card goes; on a phone its width broke
    // the course name onto two lines. One link to the editor per card.
    const toEditor = screen.getAllByRole("link").filter((a) => a.getAttribute("href") === `/teacher/courses/${course.id}`)
    expect(toEditor).toHaveLength(1)
  })
})

describe("CourseCard — a teacher looking for their students", () => {
  // Session replays, 2026-09-20 and 2026-10-15: a teacher on a phone tapped
  // the cover, the "Published" badge and the space beside the name, and
  // nothing answered; the students were the fourth item of the "…" menu.
  it("opens the course from anywhere on the card, through the one link it has", async () => {
    await i18n.changeLanguage("ru")
    const course = makeCourse()
    renderCard(0, course)

    const name = screen.getByRole("link", { name: course.title })
    // The name's ::after covers the card; the card is its positioning box.
    expect(name.className).toMatch(/(?<![\w-])after:absolute(?![\w-])/)
    expect(name.className).toMatch(/(?<![\w-])after:inset-0(?![\w-])/)
    expect(name.closest(".relative")).not.toBeNull()
  })

  it("keeps every other control tappable above the card's link", async () => {
    await i18n.changeLanguage("ru")
    const course = makeCourse()
    renderCard(2, course)

    const others = screen
      .getAllByRole("link")
      .filter((a) => a.getAttribute("href") !== `/teacher/courses/${course.id}`)
    expect(others.length).toBeGreaterThan(0)
    for (const link of others) {
      expect(link.closest(".z-10"), `${link.getAttribute("href")} sits under the card link`).not.toBeNull()
    }
    expect(screen.getByRole("button", { name: "Ещё действия" }).closest(".z-10")).not.toBeNull()
  })

  it("puts the students one tap away on every width, by name", async () => {
    await i18n.changeLanguage("ru")
    const course = makeCourse()
    renderCard(0, course)

    const students = screen.getByRole("link", { name: "Студенты" })
    expect(students).toHaveAttribute("href", `/teacher/courses/${course.id}/progress`)
    // Not hidden on a phone, and a finger-sized target there.
    expect(students.className).not.toMatch(/(?<![\w:-])hidden(?![\w-])/)
    expect(students.className).toMatch(/(?<![\w:-])min-h-11(?![\w-])/)
  })
})
