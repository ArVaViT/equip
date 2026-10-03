import type { ReactNode } from "react"
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { I18nextProvider } from "react-i18next"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"

import i18n from "@/i18n/config"
import type { Chapter, ChapterBlock, Cohort, Course } from "@/types"

/**
 * Signed in, not enrolled, on a course whose first lesson is open.
 *
 * The lesson page asked such a reader to enrol — at the end of the preview
 * and on the wall before every other lesson — and the button was a link to
 * the course page. The course page then offered the same button, and once
 * pressed, left the reader to find the lesson again. The button enrols here.
 */

const getCourse = vi.fn<(id: string) => Promise<Course>>()
const getMyChapterProgress = vi.fn<(id: string) => Promise<string[]>>()
const getChapterBlocks = vi.fn<(id: string) => Promise<ChapterBlock[]>>()
const getCourseCohorts = vi.fn<(id: string) => Promise<Cohort[]>>()
const enrollInCourse = vi.fn<(id: string, cohortId?: string) => Promise<unknown>>()

vi.mock("@/services/courses", () => ({
  coursesService: {
    getCourse: (id: string) => getCourse(id),
    getMyChapterProgress: (id: string) => getMyChapterProgress(id),
    getChapterBlocks: (id: string) => getChapterBlocks(id),
    getCourseCohorts: (id: string) => getCourseCohorts(id),
    enrollInCourse: (id: string, cohortId?: string) => enrollInCourse(id, cohortId),
  },
}))
vi.mock("@/services/progress", () => ({ progressService: { markRead: vi.fn() } }))
vi.mock("@/services/storage", () => ({ storageService: {} }))
// Once enrolled the lesson shows the reader's margin note, which reads it
// on mount: an empty one here.
vi.mock("@/services/notes", () => ({
  NOTE_MAX_LENGTH: 4000,
  notesService: { get: vi.fn().mockResolvedValue({ body: "" }) },
}))
vi.mock("@/context/useAuth", () => ({
  useAuth: () => ({ user: { id: "u-1", role: "student" } }),
}))
vi.mock("@/hooks/useUserTour", () => ({ useUserTour: () => {} }))
vi.mock("@/lib/recentlyViewed", () => ({ recordCourseView: () => {} }))
const toast = vi.fn()
vi.mock("@/lib/toast", () => ({ toast: (o: unknown) => toast(o) }))

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

/** Two lessons, the first open to anyone not enrolled. */
const PREVIEWED: Course = {
  id: "c1",
  access_mode: "public",
  enrollment_start: null,
  enrollment_end: null,
  preview_chapter_id: "l1",
  modules: [],
  chapters: [
    chapter({ id: "l1", title: "Pentecost", order_index: 0 }),
    chapter({ id: "l2", title: "The first sermon", order_index: 1 }),
  ],
} as unknown as Course

const textBlock = (id: string, html: string): ChapterBlock =>
  ({ id, chapter_id: "l1", block_type: "text", order_index: 0, content: html }) as ChapterBlock

function Wrapper({ children }: { children: ReactNode }) {
  return <I18nextProvider i18n={i18n}>{children}</I18nextProvider>
}

function open(path: string) {
  render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/courses/:courseId/chapters/:chapterId" element={<ChapterView />} />
        <Route path="/courses/:courseId" element={<p>course page</p>} />
      </Routes>
    </MemoryRouter>,
    { wrapper: Wrapper },
  )
}

beforeEach(async () => {
  await i18n.changeLanguage("en")
  vi.clearAllMocks()
  getCourse.mockResolvedValue(PREVIEWED)
  getMyChapterProgress.mockResolvedValue([])
  getCourseCohorts.mockResolvedValue([])
  enrollInCourse.mockResolvedValue({})
  // The server hands the preview's text to anyone and refuses the rest until
  // enrolled; here «enrolled» is whether the button has been pressed.
  getChapterBlocks.mockImplementation(async (id) => {
    if (id === "l1") return [textBlock("b1", "<p>Tongues of fire.</p>")]
    if (enrollInCourse.mock.calls.length > 0) return [textBlock("b2", "<p>Peter stood up.</p>")]
    throw Object.assign(new Error("forbidden"), { response: { status: 403 } })
  })
})

describe("enrolling from the lesson", () => {
  it("from the wall: one press, and the lesson that was refused opens", async () => {
    open("/courses/c1/chapters/l2")
    await screen.findByRole("heading", { level: 1, name: "The first sermon" })
    expect(screen.getByText("This lesson is for enrolled readers")).toBeInTheDocument()

    await userEvent.click(await screen.findByRole("button", { name: "Enroll in the course" }))

    expect(enrollInCourse).toHaveBeenCalledWith("c1", undefined)
    expect(await screen.findByText("Peter stood up.")).toBeInTheDocument()
    expect(screen.queryByText("This lesson is for enrolled readers")).not.toBeInTheDocument()
    expect(toast).toHaveBeenCalledWith({ title: "You're enrolled", variant: "success" })
    // No longer previewing: the lesson can be marked read like any other.
    expect(screen.getByRole("button", { name: /Mark as read/i })).toBeInTheDocument()
  })

  it("from the end of the preview: enrols and steps on to the next lesson", async () => {
    open("/courses/c1/chapters/l1")
    await screen.findByText("Tongues of fire.")
    expect(screen.getByText("Enjoyed it? Enroll in the course")).toBeInTheDocument()

    await userEvent.click(await screen.findByRole("button", { name: "Enroll in the course" }))

    expect(await screen.findByRole("heading", { level: 1, name: "The first sermon" })).toBeInTheDocument()
    expect(await screen.findByText("Peter stood up.")).toBeInTheDocument()
    expect(screen.queryByText(/Enjoyed it\?/)).not.toBeInTheDocument()
  })

  it("asks for the cohorts only for a reader it offers the button to", async () => {
    open("/courses/c1/chapters/l1")
    await screen.findByText("Tongues of fire.")
    await waitFor(() => expect(getCourseCohorts).toHaveBeenCalledWith("c1"))
  })

  it("keeps the link to the course page when a cohort has to be chosen", async () => {
    const cohort = (id: string) =>
      ({ id, status: "active", enrollment_start: "2000-01-01T00:00:00Z", enrollment_end: "2999-01-01T00:00:00Z" }) as Cohort
    getCourseCohorts.mockResolvedValue([cohort("k1"), cohort("k2")])
    open("/courses/c1/chapters/l2")
    await screen.findByRole("heading", { level: 1, name: "The first sermon" })
    expect(await screen.findByRole("link", { name: "Enroll in the course" })).toHaveAttribute("href", "/courses/c1")
    expect(enrollInCourse).not.toHaveBeenCalled()
  })
})
