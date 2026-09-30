import type { ReactNode } from "react"
import { useEffect } from "react"
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"

vi.mock("@/lib/supabase", () => ({
  supabase: {
    auth: {
      getSession: vi.fn().mockResolvedValue({ data: { session: null } }),
      refreshSession: vi.fn(),
      signOut: vi.fn(),
      onAuthStateChange: vi.fn().mockReturnValue({ data: { subscription: { unsubscribe: vi.fn() } } }),
    },
  },
}))
vi.mock("@/lib/toast", () => ({ toast: vi.fn() }))
vi.mock("@/hooks/useUserTour", () => ({ useUserTour: vi.fn() }))
vi.mock("@/components/editor/ChapterBlockEditor", () => ({ default: () => null }))
vi.mock("@/components/assignment/AssignmentEditor", () => ({ default: () => null }))
// A quiz with questions typed and not saved.
vi.mock("@/components/quiz/QuizEditor", () => ({
  default: function DirtyQuizEditor({ onDirtyChange }: { onDirtyChange?: (dirty: boolean) => void }) {
    useEffect(() => onDirtyChange?.(true), [onDirtyChange])
    return null
  },
}))

import { I18nextProvider } from "react-i18next"
import { MemoryRouter, Route, Routes } from "react-router-dom"

import i18n from "@/i18n/config"
import { ConfirmProvider } from "@/components/ui/alert-dialog"
import { coursesService } from "@/services/courses"
import type { Chapter } from "@/types"
import ChapterEditor from "../ChapterEditor"

function Wrapper({ children }: { children: ReactNode }) {
  return (
    <I18nextProvider i18n={i18n}>
      <ConfirmProvider>{children}</ConfirmProvider>
    </I18nextProvider>
  )
}

/**
 * Quiz ↔ exam keeps the same editor but reloads the quiz from the server,
 * so switching with unsaved questions lost them without a word. It asks
 * first now (2026-09-29).
 */
describe("switching a quiz with unsaved questions to an exam", () => {
  beforeEach(async () => {
    vi.restoreAllMocks()
    await i18n.changeLanguage("ru")
    vi.spyOn(coursesService, "getChapterForEdit").mockResolvedValue({
      id: "ch-1",
      module_id: null,
      title: "Проверка",
      chapter_type: "quiz",
      order_index: 0,
      is_locked: false,
    } as Chapter)
  })

  it("asks first, and staying keeps the quiz", async () => {
    render(
      <MemoryRouter initialEntries={["/teacher/courses/c-1/chapters/ch-1/edit"]}>
        <Routes>
          <Route path="/teacher/courses/:courseId/chapters/:chapterId/edit" element={<ChapterEditor />} />
        </Routes>
      </MemoryRouter>,
      { wrapper: Wrapper },
    )
    await userEvent.click(await screen.findByRole("button", { name: /Изменить/ }))
    await userEvent.click(screen.getByRole("button", { name: new RegExp(i18n.t("chapterTypes.exam.label")) }))

    expect(await screen.findByText(i18n.t("chapterEditor.typeChangeUnsaved.title"))).toBeInTheDocument()
    await userEvent.click(screen.getByRole("button", { name: i18n.t("common.cancel") }))

    await waitFor(() =>
      expect(screen.queryByText(i18n.t("chapterEditor.typeChangeUnsaved.title"))).not.toBeInTheDocument(),
    )
    // Still a quiz: opened again, the picker has the quiz marked.
    if (screen.queryAllByRole("button", { pressed: true }).length === 0) {
      await userEvent.click(screen.getByRole("button", { name: /Изменить/ }))
    }
    const pressed = screen.getAllByRole("button", { pressed: true })
    expect(pressed.map((b) => b.textContent)).toEqual([expect.stringMatching(new RegExp(i18n.t("chapterTypes.quiz.label")))])
  })
})
