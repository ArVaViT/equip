import type { ReactNode } from "react"
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"

// ``services/api`` (reached through ``services/courses``) builds the
// supabase client at module load from ``VITE_SUPABASE_*``. Mock it before
// any other import so the test never depends on the real env vars.
vi.mock("@/lib/supabase", () => ({
  supabase: {
    auth: {
      getSession: vi.fn().mockResolvedValue({ data: { session: null } }),
      refreshSession: vi.fn(),
      signOut: vi.fn(),
      onAuthStateChange: vi
        .fn()
        .mockReturnValue({ data: { subscription: { unsubscribe: vi.fn() } } }),
    },
  },
}))

vi.mock("@/lib/toast", () => ({ toast: vi.fn() }))
vi.mock("@/hooks/useUserTour", () => ({ useUserTour: vi.fn() }))
// The three type-specific editors each open their own network work and
// none of it is what this file is about.
vi.mock("@/components/editor/ChapterBlockEditor", () => ({ default: () => null }))
vi.mock("@/components/quiz/QuizEditor", () => ({ default: () => null }))
vi.mock("@/components/assignment/AssignmentEditor", () => ({ default: () => null }))

import { I18nextProvider } from "react-i18next"
import { MemoryRouter, Route, Routes } from "react-router-dom"

import i18n from "@/i18n/config"
import { ConfirmProvider } from "@/components/ui/alert-dialog"
import { coursesService } from "@/services/courses"
import type { Chapter, Module } from "@/types"
import ChapterEditor from "../ChapterEditor"

/**
 * A lesson belongs to its course, so the editor has to open from the course
 * and its address must not carry a module the lesson may not have.
 *
 * Before this, the page fetched the module and picked the lesson out of the
 * list — which has no answer at all for a lesson written straight into the
 * course, and would show the wrong module for a lesson that had since been
 * moved.
 */

function chapter(over: Partial<Chapter> = {}): Chapter {
  return {
    id: "ch-1",
    module_id: null,
    title: "Кто написал послание",
    chapter_type: "reading",
    order_index: 0,
    is_locked: false,
    ...over,
  } as Chapter
}

function Wrapper({ children }: { children: ReactNode }) {
  return (
    <I18nextProvider i18n={i18n}>
      <ConfirmProvider>{children}</ConfirmProvider>
    </I18nextProvider>
  )
}

/** Mount at the course-shaped address — the one with no module in it. */
function renderAtCourseRoute() {
  return render(
    <MemoryRouter initialEntries={["/teacher/courses/c-1/chapters/ch-1/edit"]}>
      <Routes>
        <Route
          path="/teacher/courses/:courseId/chapters/:chapterId/edit"
          element={<ChapterEditor />}
        />
      </Routes>
    </MemoryRouter>,
    { wrapper: Wrapper },
  )
}

describe("ChapterEditor — addressed by its course", () => {
  beforeEach(async () => {
    vi.restoreAllMocks()
    await i18n.changeLanguage("ru")
  })

  it("opens a lesson that is in no module, and asks for it by id", async () => {
    const get = vi
      .spyOn(coursesService, "getChapterForEdit")
      .mockResolvedValue(chapter())
    const getModule = vi.spyOn(coursesService, "getModuleForEdit")

    renderAtCourseRoute()

    await waitFor(() =>
      expect(screen.getByDisplayValue("Кто написал послание")).toBeInTheDocument(),
    )
    expect(get).toHaveBeenCalledWith("c-1", "ch-1")
    // Nothing to ask a module about, so nothing is asked.
    expect(getModule).not.toHaveBeenCalled()
  })

  it("leads back to the course, not to a module the lesson never had", async () => {
    vi.spyOn(coursesService, "getChapterForEdit").mockResolvedValue(chapter())

    renderAtCourseRoute()
    await waitFor(() =>
      expect(screen.getByDisplayValue("Кто написал послание")).toBeInTheDocument(),
    )

    // Breadcrumb: «Мои курсы › Курс › Кто написал послание» — three crumbs,
    // no invented heading in the middle.
    const crumbs = screen.getAllByRole("link").map((a) => a.getAttribute("href"))
    expect(crumbs).toEqual(["/teacher", "/teacher/courses/c-1"])
  })

  it("names the module in the breadcrumb when the lesson is in one", async () => {
    vi.spyOn(coursesService, "getChapterForEdit").mockResolvedValue(
      chapter({ module_id: "m-1" }),
    )
    vi.spyOn(coursesService, "getModuleForEdit").mockResolvedValue({
      id: "m-1",
      title: "Часть первая",
    } as Module)

    renderAtCourseRoute()

    await waitFor(() => expect(screen.getByText("Часть первая")).toBeInTheDocument())
    const crumbs = screen.getAllByRole("link").map((a) => a.getAttribute("href"))
    expect(crumbs).toContain("/teacher/courses/c-1/modules/m-1/edit")
  })

  it("saves without touching the grouping", async () => {
    vi.spyOn(coursesService, "getChapterForEdit").mockResolvedValue(
      chapter({ module_id: "m-1" }),
    )
    vi.spyOn(coursesService, "getModuleForEdit").mockResolvedValue({
      id: "m-1",
      title: "Часть первая",
    } as Module)
    const update = vi
      .spyOn(coursesService, "updateCourseChapter")
      .mockResolvedValue(chapter({ module_id: "m-1" }))

    renderAtCourseRoute()
    await waitFor(() =>
      expect(screen.getByDisplayValue("Кто написал послание")).toBeInTheDocument(),
    )

    await userEvent.click(screen.getByRole("button", { name: "Сохранить урок" }))

    await waitFor(() => expect(update).toHaveBeenCalled())
    const [courseId, chapterId, payload] = update.mock.calls[0]!
    expect(courseId).toBe("c-1")
    expect(chapterId).toBe("ch-1")
    // An explicit ``null`` here would lift the lesson out of its module on
    // every save; the key has to be absent for "leave the grouping alone".
    expect(payload).not.toHaveProperty("module_id")
  })
})
