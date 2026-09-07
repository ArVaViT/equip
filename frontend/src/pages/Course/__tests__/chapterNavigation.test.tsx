import type { ReactNode } from "react"
import { render, screen, waitFor } from "@testing-library/react"
import { I18nextProvider } from "react-i18next"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"

import i18n from "@/i18n/config"
import type { Chapter, ChapterBlock, Course, Module } from "@/types"

/**
 * What "next" means on a lesson page.
 *
 * It used to mean "the next chapter of this module", and that answer ran out
 * in two places at once:
 *
 * - at a module's last lesson, where a second rule had to be invented to say
 *   "and now the next module";
 * - and on a lesson in no module, where there was no first rule to run out —
 *   no module to sort, no neighbours, no "next" under any reading of the code.
 *
 * It means "the next lesson of the course" now, and the tests below are the
 * two courses that proves it on: one built the old way, all lessons inside
 * modules, and one built the way the first live teacher wanted to build his —
 * four lessons and nothing else.
 */

const getCourse = vi.fn<(id: string) => Promise<Course>>()
const getMyChapterProgress = vi.fn<(id: string) => Promise<string[]>>()
const getChapterBlocks = vi.fn<(id: string) => Promise<ChapterBlock[]>>()

vi.mock("@/services/courses", () => ({
  coursesService: {
    getCourse: (id: string) => getCourse(id),
    getMyChapterProgress: (id: string) => getMyChapterProgress(id),
    getChapterBlocks: (id: string) => getChapterBlocks(id),
  },
}))

vi.mock("@/services/progress", () => ({ progressService: { markRead: vi.fn() } }))
vi.mock("@/services/storage", () => ({ storageService: {} }))
vi.mock("@/context/useAuth", () => ({
  useAuth: () => ({ user: { id: "u-1", role: "student" } }),
}))
vi.mock("@/hooks/useUserTour", () => ({ useUserTour: () => {} }))
vi.mock("@/lib/recentlyViewed", () => ({ recordCourseView: () => {} }))

// Imported after the mocks, so the module graph it pulls in is the mocked one.
const { default: ChapterView } = await import("../ChapterView")

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

/** Everything in modules, the only shape a course could have before. */
const GROUPED: Course = {
  id: "c1",
  modules: [
    module_({
      id: "m1",
      title: "Beginnings",
      order_index: 0,
      chapters: [
        chapter({ id: "a1", module_id: "m1", title: "Pentecost", order_index: 0 }),
        chapter({ id: "a2", module_id: "m1", title: "The first sermon", order_index: 1 }),
      ],
    }),
    module_({
      id: "m2",
      title: "The road out",
      order_index: 1,
      chapters: [chapter({ id: "b1", module_id: "m2", title: "Antioch", order_index: 0 })],
    }),
  ],
  chapters: [],
} as unknown as Course

/** Four lessons, no modules. */
const LOOSE: Course = {
  id: "c1",
  modules: [],
  chapters: [
    chapter({ id: "l1", title: "Pentecost", order_index: 0 }),
    chapter({ id: "l2", title: "The first sermon", order_index: 1 }),
    chapter({ id: "l3", title: "Antioch", order_index: 2 }),
    chapter({ id: "l4", title: "Breaking bread", order_index: 3 }),
  ],
} as unknown as Course

function Wrapper({ children }: { children: ReactNode }) {
  return <I18nextProvider i18n={i18n}>{children}</I18nextProvider>
}

/** Open a lesson at `path` and wait for its title to land. */
async function open(path: string, title: string) {
  render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/courses/:courseId/chapters/:chapterId" element={<ChapterView />} />
        <Route
          path="/courses/:courseId/modules/:moduleId/chapters/:chapterId"
          element={<ChapterView />}
        />
      </Routes>
    </MemoryRouter>,
    { wrapper: Wrapper },
  )
  await screen.findByRole("heading", { level: 1, name: title })
}

/** The "next" tile, by the eyebrow it carries. */
function nextTile(): HTMLElement | null {
  return screen.queryByRole("button", { name: /^Next:/ })
}

beforeEach(async () => {
  await i18n.changeLanguage("en")
  vi.clearAllMocks()
  getMyChapterProgress.mockResolvedValue([])
  getChapterBlocks.mockResolvedValue([])
})

describe("a lesson that no module groups", () => {
  beforeEach(() => {
    getCourse.mockResolvedValue(LOOSE)
  })

  it("has a next lesson at all", async () => {
    // The whole point. Under the module walk this lesson had no neighbours:
    // "next" was a greyed-out placeholder on every one of the four.
    await open("/courses/c1/chapters/l2", "The first sermon")
    expect(nextTile()).toHaveAccessibleName("Next: Antioch")
  })

  it("has a previous lesson too", async () => {
    await open("/courses/c1/chapters/l2", "The first sermon")
    expect(screen.getByRole("button", { name: "Previous: Pentecost" })).toBeInTheDocument()
  })

  it("counts the lesson against the course", async () => {
    await open("/courses/c1/chapters/l3", "Antioch")
    expect(screen.getAllByText("Chapter 3 of 4").length).toBeGreaterThan(0)
  })

  it("leads back to the course, because there is no module to lead back to", async () => {
    await open("/courses/c1/chapters/l2", "The first sermon")
    expect(screen.getByRole("link", { name: /Back to Course/ })).toHaveAttribute(
      "href",
      "/courses/c1",
    )
    expect(screen.queryByRole("link", { name: /Back to Module/ })).not.toBeInTheDocument()
  })

  it("offers the course, not a dead end, after the last lesson", async () => {
    await open("/courses/c1/chapters/l4", "Breaking bread")
    expect(
      screen.getByRole("button", { name: /Finish course: Course overview/ }),
    ).toBeInTheDocument()
  })
})

describe("a lesson inside a module", () => {
  beforeEach(() => {
    getCourse.mockResolvedValue(GROUPED)
  })

  it("steps over the module boundary into the next module's first lesson", async () => {
    // The last lesson of module one. It used to offer «Next module:
    // The road out» — a second rule, bolted on, because the walk it was
    // bolted to could not leave the module. One step, one rule.
    await open("/courses/c1/modules/m1/chapters/a2", "The first sermon")
    expect(nextTile()).toHaveAccessibleName("Next: Antioch")
  })

  it("steps backwards over it too", async () => {
    await open("/courses/c1/modules/m2/chapters/b1", "Antioch")
    expect(
      screen.getByRole("button", { name: "Previous: The first sermon" }),
    ).toBeInTheDocument()
  })

  it("still names the module it belongs to, and leads back to it", async () => {
    await open("/courses/c1/modules/m1/chapters/a1", "Pentecost")
    expect(screen.getByText("Beginnings")).toBeInTheDocument()
    expect(screen.getByRole("link", { name: /Back to Module/ })).toHaveAttribute(
      "href",
      "/courses/c1/modules/m1",
    )
  })

  it("opens from the course-shaped address as well, and knows its module from the course", async () => {
    // `moduleId` used to be required before a single request went out, so
    // this address died on a guard reading «invalid link». The lesson's place
    // is a fact about the course, not about the URL that reached it.
    await open("/courses/c1/chapters/a1", "Pentecost")
    expect(screen.getByText("Beginnings")).toBeInTheDocument()
    expect(nextTile()).toHaveAccessibleName("Next: The first sermon")
  })

  it("counts the lesson against the course, not against its module", async () => {
    // «Chapter 1 of 1» on the last module told a student they were at the
    // start of something they were three lessons into.
    await open("/courses/c1/modules/m2/chapters/b1", "Antioch")
    expect(screen.getAllByText("Chapter 3 of 3").length).toBeGreaterThan(0)
  })

  it("offers the course after the last lesson of the last module", async () => {
    await open("/courses/c1/modules/m2/chapters/b1", "Antioch")
    expect(
      screen.getByRole("button", { name: /Finish course: Course overview/ }),
    ).toBeInTheDocument()
  })
})

describe("when the course cannot be read", () => {
  it("says so and leads back to the course rather than to a module", async () => {
    getCourse.mockRejectedValue(new Error("network"))
    render(
      <MemoryRouter initialEntries={["/courses/c1/chapters/l1"]}>
        <Routes>
          <Route path="/courses/:courseId/chapters/:chapterId" element={<ChapterView />} />
        </Routes>
      </MemoryRouter>,
      { wrapper: Wrapper },
    )
    await waitFor(() =>
      expect(screen.getByRole("link", { name: /Back to Course/ })).toHaveAttribute(
        "href",
        "/courses/c1",
      ),
    )
  })
})
