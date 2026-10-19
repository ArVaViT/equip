/**
 * A refused rename goes back to the saved title. The row's `chapter.title`
 * is already the typed text when the rename is sent, so «roll back to
 * chapter.title» rolled back to nothing and the refused title stayed.
 */
import type { ReactNode } from "react"
import { act, renderHook } from "@testing-library/react"
import { I18nextProvider } from "react-i18next"
import { MemoryRouter } from "react-router-dom"
import { useState } from "react"
import { beforeEach, describe, expect, it, vi } from "vitest"

vi.mock("@/lib/toast", () => ({ toast: vi.fn() }))

import i18n from "@/i18n/config"
import { coursesService } from "@/services/courses"
import type { Chapter, Course } from "@/types"
import { useCourseChapters } from "../useCourseChapters"

const lesson = { id: "l1", course_id: "c1", module_id: null, title: "Pentecost", order_index: 0, chapter_type: "reading", is_locked: false } as Chapter
const COURSE = { id: "c1", title: "Acts", modules: [], chapters: [lesson] } as unknown as Course

function Wrapper({ children }: { children: ReactNode }) {
  return (
    <I18nextProvider i18n={i18n}>
      <MemoryRouter>{children}</MemoryRouter>
    </I18nextProvider>
  )
}

function useHarness() {
  const [course, setCourse] = useState<Course | null>(COURSE)
  const chapters = useCourseChapters({ courseId: "c1", course, setCourse })
  return { course, ...chapters }
}

describe("useCourseChapters.renameChapter", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("en")
    vi.restoreAllMocks()
  })

  it("shows the saved title again when the server refuses the new one", async () => {
    vi.spyOn(coursesService, "updateCourseChapter").mockRejectedValue(
      Object.assign(new Error("Conflict"), { isAxiosError: true, response: { status: 409, data: {} } }),
    )
    const { result } = renderHook(useHarness, { wrapper: Wrapper })
    // Keystrokes land in the course first, as the row's controlled input does.
    act(() => result.current.updateChapterLocal("l1", { title: "Pentecost, revised" }))
    const typed = result.current.course!.chapters![0]!
    expect(typed.title).toBe("Pentecost, revised")

    await act(async () => {
      await result.current.renameChapter(typed, "Pentecost, revised", "Pentecost")
    })
    expect(result.current.course!.chapters![0]!.title).toBe("Pentecost")
  })

  it("keeps the new title when the server took it", async () => {
    vi.spyOn(coursesService, "updateCourseChapter").mockResolvedValue({ ...lesson, title: "Pentecost, revised" } as never)
    const { result } = renderHook(useHarness, { wrapper: Wrapper })
    act(() => result.current.updateChapterLocal("l1", { title: "Pentecost, revised" }))
    await act(async () => {
      await result.current.renameChapter(result.current.course!.chapters![0]!, "Pentecost, revised", "Pentecost")
    })
    expect(result.current.course!.chapters![0]!.title).toBe("Pentecost, revised")
  })
})
