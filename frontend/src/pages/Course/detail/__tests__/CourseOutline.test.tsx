import type { ReactNode } from "react"
import { render, screen, within } from "@testing-library/react"
import { I18nextProvider } from "react-i18next"
import { MemoryRouter } from "react-router-dom"
import { beforeEach, describe, expect, it } from "vitest"

import i18n from "@/i18n/config"
import { readCourseStructure } from "@/lib/courseStructure"
import { CourseOutline } from "../CourseOutline"
import type { Chapter, Course, Module } from "@/types"

/**
 * The course page's outline, for the course that started this: four lessons
 * and no modules.
 *
 * The screen this replaces could only draw modules. A course whose lessons sit
 * in no module rendered «Модули (0)» over «преподаватель не опубликовал
 * модулей» — the page telling a student their four lessons do not exist, and
 * telling their teacher to invent a container to hold them. That is what the
 * first live teacher did.
 */

function Wrapper({ children }: { children: ReactNode }) {
  return (
    <I18nextProvider i18n={i18n}>
      <MemoryRouter>{children}</MemoryRouter>
    </I18nextProvider>
  )
}

const chapter = (over: Partial<Chapter>): Chapter =>
  ({
    course_id: "c1",
    module_id: null,
    order_index: 0,
    chapter_type: "reading",
    requires_completion: false,
    is_locked: false,
    ...over,
  }) as Chapter

const module_ = (over: Partial<Module>): Module =>
  ({
    course_id: "c1",
    description: null,
    order_index: 0,
    due_date: null,
    chapters: [],
    ...over,
  }) as Module

function course(over: Partial<Course>): Course {
  return { id: "c1", modules: [], chapters: [], ...over } as unknown as Course
}

function show(c: Course, completed: Set<string> | null = new Set()) {
  return render(
    <CourseOutline
      courseId="c1"
      structure={readCourseStructure(c)}
      completedChapterIds={completed}
    />,
    { wrapper: Wrapper },
  )
}

/** Four lessons written straight into the course. */
const FOUR_LESSONS = course({
  chapters: [
    chapter({ id: "l1", title: "Pentecost", order_index: 0 }),
    chapter({ id: "l2", title: "The first sermon", order_index: 1 }),
    chapter({ id: "l3", title: "Quiz on Acts 2", order_index: 2, chapter_type: "quiz" }),
    chapter({ id: "l4", title: "Breaking bread", order_index: 3, is_locked: true }),
  ],
})

/** The course as it had to be built before: everything inside a module. */
const TWO_MODULES = course({
  modules: [
    module_({
      id: "m1",
      title: "Beginnings",
      order_index: 0,
      chapters: [
        chapter({ id: "a1", module_id: "m1", title: "Pentecost", order_index: 0 }),
        chapter({
          id: "a2",
          module_id: "m1",
          title: "Quiz on Acts 2",
          order_index: 1,
          chapter_type: "quiz",
        }),
      ],
    }),
    module_({
      id: "m2",
      title: "The road out",
      order_index: 1,
      chapters: [chapter({ id: "b1", module_id: "m2", title: "Antioch", order_index: 0 })],
    }),
  ],
})

beforeEach(async () => {
  await i18n.changeLanguage("en")
})

describe("a course of lessons and no modules", () => {
  it("is its lessons, and never mentions a module", () => {
    const { container } = show(FOUR_LESSONS)

    expect(screen.getByRole("heading", { name: /Lessons\s*\(4\)/ })).toBeInTheDocument()
    for (const title of ["Pentecost", "The first sermon", "Quiz on Acts 2", "Breaking bread"]) {
      expect(screen.getByText(title)).toBeInTheDocument()
    }
    // The word the course does not use appears nowhere on it.
    expect(container.textContent ?? "").not.toMatch(/module/i)
  })

  it("links each lesson by its course, which is the address it always has", () => {
    show(FOUR_LESSONS)
    expect(screen.getByRole("link", { name: /Pentecost/ })).toHaveAttribute(
      "href",
      "/courses/c1/chapters/l1",
    )
  })

  it("says the course has no lessons yet, not that it has no modules", () => {
    const { container } = show(course({}))
    expect(screen.getByText("No lessons yet")).toBeInTheDocument()
    expect(container.textContent ?? "").not.toMatch(/module/i)
  })
})

describe("what stands between a student and the next lesson", () => {
  it("locks a gated lesson while the assessment before it is unfinished", () => {
    // `l4` is gated and `l3` is a quiz: until the quiz is passed, `l4` is
    // shut. This rule existed only inside a module before — a lesson in no
    // module had no previous lesson under any rule, so nothing was ever
    // locked and `is_locked` meant nothing.
    show(FOUR_LESSONS)

    expect(screen.getByText("Locked")).toBeInTheDocument()
    expect(screen.queryByRole("link", { name: /Breaking bread/ })).not.toBeInTheDocument()
    expect(screen.getByText(/Finish the previous lesson/)).toBeInTheDocument()
  })

  it("opens it once that assessment is done", () => {
    show(FOUR_LESSONS, new Set(["l3"]))

    expect(screen.queryByText("Locked")).not.toBeInTheDocument()
    expect(screen.getByRole("link", { name: /Breaking bread/ })).toHaveAttribute(
      "href",
      "/courses/c1/chapters/l4",
    )
  })

  it("opens it when the progress request failed, rather than walling somebody out on a guess", () => {
    // `null` is "we could not find out", and it must not read as "you have
    // finished nothing". The server is the real gate; being wrong in this
    // direction costs a student nothing they earned.
    show(FOUR_LESSONS, null)
    expect(screen.queryByText("Locked")).not.toBeInTheDocument()
  })

  it("explains the rule once, next to the first door it applies to", () => {
    show(
      course({
        chapters: [
          chapter({ id: "q1", title: "Quiz one", order_index: 0, chapter_type: "quiz" }),
          chapter({ id: "g1", title: "Gated one", order_index: 1, is_locked: true }),
          chapter({ id: "q2", title: "Quiz two", order_index: 2, chapter_type: "quiz" }),
          chapter({ id: "g2", title: "Gated two", order_index: 3, is_locked: true }),
        ],
      }),
    )

    expect(screen.getAllByText("Locked")).toHaveLength(2)
    expect(screen.getAllByText(/Finish the previous lesson/)).toHaveLength(1)
  })
})

describe("a course that does group its lessons", () => {
  it("still reads as its modules", () => {
    show(TWO_MODULES)

    expect(screen.getByRole("heading", { name: /Modules\s*\(2\)/ })).toBeInTheDocument()
    expect(screen.getByText("Beginnings")).toBeInTheDocument()
    expect(screen.getByText("The road out")).toBeInTheDocument()
    // The lessons stay behind their module's own page, as they were.
    expect(screen.queryByText("Pentecost")).not.toBeInTheDocument()
    expect(screen.getAllByRole("link", { name: /Open/ })[0]).toHaveAttribute(
      "href",
      "/courses/c1/modules/m1",
    )
  })

  it("still locks a module behind the one before it", () => {
    show(TWO_MODULES)

    expect(screen.getByText("Locked")).toBeInTheDocument()
    expect(screen.getByText(/Complete all assessments in the previous module/)).toBeInTheDocument()
    expect(screen.queryByRole("link", { name: /^Open/ })).toHaveAttribute(
      "href",
      "/courses/c1/modules/m1",
    )
  })

  it("unlocks it once that module's assessments are done", () => {
    show(TWO_MODULES, new Set(["a2"]))
    expect(screen.queryByText("Locked")).not.toBeInTheDocument()
  })

  it("counts a module's assessments, not its lessons, on the row", () => {
    show(TWO_MODULES, new Set(["a2"]))
    const beginnings = screen.getByText("Beginnings").closest("div")!
    expect(within(beginnings).getByText("1/1")).toBeInTheDocument()
  })
})

describe("a course that does both", () => {
  it("shows the modules and then the lessons no module holds", () => {
    const mixed = course({
      modules: [TWO_MODULES.modules![0]!],
      chapters: [chapter({ id: "loose", title: "A closing word", order_index: 0 })],
    })
    const { container } = show(mixed)

    // Counted in lessons, because that is the only unit the two halves share.
    expect(screen.getByRole("heading", { name: /Contents\s*\(3\)/ })).toBeInTheDocument()
    expect(screen.getByText("Beginnings")).toBeInTheDocument()
    expect(screen.getByRole("link", { name: /A closing word/ })).toHaveAttribute(
      "href",
      "/courses/c1/chapters/loose",
    )
    // The loose lesson is third in the course, and its row says so rather
    // than restarting the count.
    expect(container.textContent).toMatch(/3A closing word/)
  })
})
