import type { ReactNode } from "react"
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { I18nextProvider } from "react-i18next"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"

import i18n from "@/i18n/config"
import type { Chapter, ChapterBlock, Course } from "@/types"

/**
 * «Mark as read» saved, then the progress refresh behind it failed — and the
 * button came back as if nothing had been saved. The student pressed it
 * again; the server answered the same; the button came back again.
 */

const getCourse = vi.fn<(id: string) => Promise<Course>>()
const getMyChapterProgress = vi.fn<(id: string) => Promise<string[]>>()
const getChapterBlocks = vi.fn<(id: string) => Promise<ChapterBlock[]>>()
const markRead = vi.fn<(id: string) => Promise<unknown>>()

vi.mock("@/services/courses", () => ({
  coursesService: {
    getCourse: (id: string) => getCourse(id),
    getMyChapterProgress: (id: string) => getMyChapterProgress(id),
    getChapterBlocks: (id: string) => getChapterBlocks(id),
  },
}))
vi.mock("@/services/progress", () => ({ progressService: { markRead: (id: string) => markRead(id) } }))
vi.mock("@/services/storage", () => ({ storageService: {} }))
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

const COURSE: Course = {
  id: "c1",
  access_mode: "public",
  enrollment_start: null,
  enrollment_end: null,
  preview_chapter_id: null,
  modules: [],
  chapters: [
    {
      id: "l1",
      course_id: "c1",
      module_id: null,
      title: "Pentecost",
      order_index: 0,
      chapter_type: "reading",
      requires_completion: false,
      is_locked: false,
    } as Chapter,
  ],
} as unknown as Course

function Wrapper({ children }: { children: ReactNode }) {
  return <I18nextProvider i18n={i18n}>{children}</I18nextProvider>
}

beforeEach(async () => {
  await i18n.changeLanguage("en")
  vi.clearAllMocks()
  getCourse.mockResolvedValue(COURSE)
  getChapterBlocks.mockResolvedValue([
    { id: "b1", chapter_id: "l1", block_type: "text", order_index: 0, content: "<p>Tongues of fire.</p>" } as ChapterBlock,
  ])
  markRead.mockResolvedValue({})
})

describe("marking a lesson read", () => {
  it("stays read when the progress refresh after the save fails", async () => {
    getMyChapterProgress.mockResolvedValueOnce([]).mockRejectedValue(new Error("offline"))
    render(
      <MemoryRouter initialEntries={["/courses/c1/chapters/l1"]}>
        <Routes>
          <Route path="/courses/:courseId/chapters/:chapterId" element={<ChapterView />} />
        </Routes>
      </MemoryRouter>,
      { wrapper: Wrapper },
    )

    await userEvent.click(await screen.findByRole("button", { name: /Mark as read/i }))

    await waitFor(() => expect(markRead).toHaveBeenCalledWith("l1"))
    expect(await screen.findByText("Lesson read")).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: /Mark as read/i })).not.toBeInTheDocument()
    expect(toast).not.toHaveBeenCalled()
  })
})
