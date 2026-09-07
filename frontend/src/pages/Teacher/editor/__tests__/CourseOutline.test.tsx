import type { ReactNode } from "react"
import { render, screen } from "@testing-library/react"
import { I18nextProvider } from "react-i18next"
import { MemoryRouter } from "react-router-dom"
import { describe, expect, it, vi } from "vitest"

import i18n from "@/i18n/config"
import { readCourseStructure } from "@/lib/courseStructure"
import type { Chapter, Course, Module } from "@/types"
import { CourseOutline } from "../CourseOutline"

/**
 * The promise this screen makes: a teacher whose course is four lessons
 * builds it end to end without ever reading the word "module".
 *
 * That is not a wording preference. The first teacher on the platform had a
 * four-lesson course, was shown a screen that could only add modules,
 * invented one to hold his lessons, reshaped the tree twice trying to make
 * it fit, and deleted the lessons in the process. The word on screen is
 * what sent him there.
 */

function chapter(over: Partial<Chapter> = {}): Chapter {
  return {
    id: "ch-1",
    module_id: null,
    title: "Урок",
    chapter_type: "reading",
    order_index: 0,
    is_locked: false,
    requires_completion: false,
    created_at: "2025-01-01T00:00:00Z",
    updated_at: null,
    deleted_at: null,
    ...over,
  } as Chapter
}

function module_(over: Partial<Module> = {}): Module {
  return {
    id: "m-1",
    course_id: "c-1",
    title: "Часть первая",
    description: null,
    order_index: 0,
    due_date: null,
    chapters: [],
    created_at: "2025-01-01T00:00:00Z",
    updated_at: null,
    deleted_at: null,
    ...over,
  } as Module
}

function course(over: Partial<Course> = {}): Course {
  return {
    id: "c-1",
    title: "Послание к Римлянам",
    description: null,
    image_url: null,
    status: "draft",
    access_mode: "public",
    created_by: "teacher-1",
    created_at: "2025-01-01T00:00:00Z",
    updated_at: null,
    deleted_at: null,
    enrollment_start: null,
    enrollment_end: null,
    modules: [],
    chapters: [],
    ...over,
  } as Course
}

function Wrapper({ children }: { children: ReactNode }) {
  return (
    <I18nextProvider i18n={i18n}>
      <MemoryRouter>{children}</MemoryRouter>
    </I18nextProvider>
  )
}

function renderOutline(c: Course) {
  const modules = [...(c.modules ?? [])].sort((a, b) => a.order_index - b.order_index)
  return render(
    <CourseOutline
      courseId={c.id}
      structure={readCourseStructure(c)}
      modules={modules}
      onModuleDragEnd={vi.fn()}
      onChapterDragEnd={vi.fn()}
      onAddModule={vi.fn()}
      onAddChapter={vi.fn()}
      onRemoveModule={vi.fn()}
      onChapterTitleChange={vi.fn()}
      onRenameChapter={vi.fn()}
      onToggleChapterLock={vi.fn()}
      onDeleteChapter={vi.fn()}
      onMoveChapter={vi.fn()}
    />,
    { wrapper: Wrapper },
  )
}

/**
 * Cyrillic has no `\b` in JavaScript regexes — `\b` is defined over `\w`,
 * which is ASCII — so a word boundary has to be spelled with lookaround
 * over the Unicode letter class.
 */
const MODULE_WORD = /(?<!\p{L})модул\p{L}*/iu

const FOUR_LESSONS = course({
  chapters: [
    chapter({ id: "ch-1", title: "Кто написал послание", order_index: 0 }),
    chapter({ id: "ch-2", title: "Рим в первом веке", order_index: 1 }),
    chapter({ id: "ch-3", title: "Оправдание верой", order_index: 2 }),
    chapter({ id: "ch-4", title: "Жизнь в Духе", order_index: 3 }),
  ],
})

describe("CourseOutline — a course that is only lessons", () => {
  it("shows the four lessons and never says «модуль»", async () => {
    await i18n.changeLanguage("ru")
    const { container } = renderOutline(FOUR_LESSONS)

    for (const title of [
      "Кто написал послание",
      "Рим в первом веке",
      "Оправдание верой",
      "Жизнь в Духе",
    ]) {
      expect(screen.getByDisplayValue(title)).toBeInTheDocument()
    }

    // Everything on screen, including the aria-labels a screen reader
    // announces — not just the visible text.
    const spoken = [
      container.textContent ?? "",
      ...Array.from(container.querySelectorAll("[aria-label]")).map(
        (el) => el.getAttribute("aria-label") ?? "",
      ),
      ...Array.from(container.querySelectorAll("[title]")).map(
        (el) => el.getAttribute("title") ?? "",
      ),
      ...Array.from(container.querySelectorAll("[placeholder]")).map(
        (el) => el.getAttribute("placeholder") ?? "",
      ),
    ].join(" ")
    expect(spoken).not.toMatch(MODULE_WORD)
  })

  it("offers no way to move a lesson when there is nothing to move it into", async () => {
    await i18n.changeLanguage("ru")
    renderOutline(FOUR_LESSONS)

    expect(screen.queryByLabelText(/Переместить урок/i)).not.toBeInTheDocument()
  })

  it("says the course has no lessons, not that it has no modules", async () => {
    await i18n.changeLanguage("ru")
    const { container } = renderOutline(course())

    expect(screen.getByText("В курсе пока нет уроков")).toBeInTheDocument()
    expect(container.textContent ?? "").not.toMatch(MODULE_WORD)
  })
})

describe("CourseOutline — a course that groups its lessons", () => {
  const mixed = course({
    modules: [
      module_({
        id: "m-1",
        title: "Часть первая",
        chapters: [chapter({ id: "ch-a", module_id: "m-1", title: "Введение", order_index: 0 })],
      }),
    ],
    chapters: [chapter({ id: "ch-b", title: "Послесловие", order_index: 5 })],
  })

  it("draws the module and the loose lesson in one list", async () => {
    await i18n.changeLanguage("ru")
    renderOutline(mixed)

    // The module keeps its heading and its count…
    expect(screen.getByText("Часть первая")).toBeInTheDocument()
    expect(screen.getByText("1 урок")).toBeInTheDocument()
    // …and the lesson that is in no module is right there beside it,
    // editable, rather than hidden behind a heading it does not have.
    expect(screen.getByDisplayValue("Послесловие")).toBeInTheDocument()
  })

  it("offers to file a loose lesson under a module once one exists", async () => {
    await i18n.changeLanguage("ru")
    renderOutline(mixed)

    expect(screen.getByLabelText(/Переместить урок «Послесловие»/i)).toBeInTheDocument()
  })
})
