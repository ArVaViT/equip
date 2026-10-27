import type { ReactNode } from "react"
import { render, screen } from "@testing-library/react"
import { I18nextProvider } from "react-i18next"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"
import i18n from "@/i18n/config"
import type { ChapterBlock, Course } from "@/types"

const mocks = vi.hoisted(() => ({
  auth: { user: null as { id: string; role: string } | null, sessionUserId: "account-a" as string | null },
  online: false,
  getCourse: vi.fn(),
  getMyChapterProgress: vi.fn(),
  getChapterBlocks: vi.fn(),
  getOfflineLesson: vi.fn(),
  saveOfflineLesson: vi.fn(),
  invalidateOfflineLesson: vi.fn(),
  invalidateOfflineUserCourse: vi.fn(),
}))

vi.mock("@/context/useAuth", () => ({ useAuth: () => mocks.auth }))
vi.mock("@/hooks/useOnlineStatus", () => ({ useOnlineStatus: () => mocks.online }))
vi.mock("@/services/courses", () => ({
  coursesService: {
    getCourse: (...args: unknown[]) => mocks.getCourse(...args),
    getMyChapterProgress: (...args: unknown[]) => mocks.getMyChapterProgress(...args),
    getChapterBlocks: (...args: unknown[]) => mocks.getChapterBlocks(...args),
  },
}))
vi.mock("@/lib/offlineLessons", () => ({
  getOfflineLesson: (...args: unknown[]) => mocks.getOfflineLesson(...args),
  saveOfflineLesson: (...args: unknown[]) => mocks.saveOfflineLesson(...args),
  invalidateOfflineLesson: (...args: unknown[]) => mocks.invalidateOfflineLesson(...args),
  invalidateOfflineUserCourse: (...args: unknown[]) => mocks.invalidateOfflineUserCourse(...args),
}))
vi.mock("@/services/progress", () => ({ progressService: { markRead: vi.fn() } }))
vi.mock("@/services/storage", () => ({ storageService: {} }))
vi.mock("@/services/notes", () => ({
  NOTE_MAX_LENGTH: 4000,
  notesService: { get: vi.fn(), save: vi.fn() },
}))
vi.mock("@/hooks/useUserTour", () => ({ useUserTour: () => {} }))
vi.mock("@/lib/recentlyViewed", () => ({ recordCourseView: vi.fn() }))
vi.mock("@/lib/toast", () => ({ toast: vi.fn() }))

const { default: ChapterView } = await import("../ChapterView")

const COURSE: Course = {
  id: "course-1",
  title: "Offline course",
  description: null,
  image_url: null,
  status: "published",
  access_mode: "public",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
  deleted_at: null,
  enrollment_start: null,
  enrollment_end: null,
  chapters: [
    {
      id: "lesson-1",
      course_id: "course-1",
      module_id: null,
      title: "Saved lesson",
      order_index: 0,
      chapter_type: "reading",
      requires_completion: false,
      is_locked: false,
    },
  ],
}

const BLOCKS: ChapterBlock[] = [
  {
    id: "text-1",
    chapter_id: "lesson-1",
    block_type: "text",
    order_index: 0,
    content: "<p>Saved reading body</p>",
    quiz_id: null,
    assignment_id: null,
    file_bucket: null,
    file_path: null,
    file_name: null,
  },
]

function Wrapper({ children }: { children: ReactNode }) {
  return <I18nextProvider i18n={i18n}>{children}</I18nextProvider>
}

beforeEach(async () => {
  await i18n.changeLanguage("en")
  mocks.auth = { user: null, sessionUserId: "account-a" }
  mocks.online = false
  vi.clearAllMocks()
  mocks.getOfflineLesson.mockResolvedValue({ course: COURSE, blocks: BLOCKS })
})

describe("offline chapter reading", () => {
  it("restores a previously cached lesson for the active account without requesting private data", async () => {
    render(
      <MemoryRouter initialEntries={["/courses/course-1/chapters/lesson-1"]}>
        <Routes>
          <Route path="/courses/:courseId/chapters/:chapterId" element={<ChapterView />} />
        </Routes>
      </MemoryRouter>,
      { wrapper: Wrapper },
    )

    expect(await screen.findByText("Saved reading body")).toBeInTheDocument()
    expect(mocks.getOfflineLesson).toHaveBeenCalledWith(
      "account-a",
      "en",
      "course-1",
      "lesson-1",
    )
    expect(mocks.getCourse).not.toHaveBeenCalled()
    expect(mocks.getChapterBlocks).not.toHaveBeenCalled()
    expect(screen.queryByRole("button", { name: /Mark as read/i })).not.toBeInTheDocument()
    expect(screen.queryByText("Add a note")).not.toBeInTheDocument()
  })

  it("does not read another account's offline copy", async () => {
    mocks.auth = { user: null, sessionUserId: "account-b" }
    mocks.getOfflineLesson.mockResolvedValue(null)

    render(
      <MemoryRouter initialEntries={["/courses/course-1/chapters/lesson-1"]}>
        <Routes>
          <Route path="/courses/:courseId/chapters/:chapterId" element={<ChapterView />} />
        </Routes>
      </MemoryRouter>,
      { wrapper: Wrapper },
    )

    expect(await screen.findByRole("alert")).toBeInTheDocument()
    expect(mocks.getOfflineLesson).toHaveBeenCalledWith(
      "account-b",
      "en",
      "course-1",
      "lesson-1",
    )
    expect(screen.queryByText("Saved reading body")).not.toBeInTheDocument()
  })
})
