import type { ReactNode } from "react"
import { render, screen } from "@testing-library/react"
import { I18nextProvider } from "react-i18next"
import { describe, expect, it, vi } from "vitest"

import i18n from "@/i18n/config"
import type { Chapter } from "@/types"
import { ChapterList } from "../ChapterList"
import type { ChapterMove } from "../ChapterRow"

/**
 * The same row serves both editors, and the move control is what makes it
 * work in both directions: out of a module (the module editor's offer) and
 * into one (the course editor's). Whether it appears at all is decided by
 * what there is to offer — never by which screen is asking.
 */

const LESSON: Chapter = {
  id: "ch-1",
  module_id: "m-1",
  title: "Кто написал послание",
  chapter_type: "reading",
  order_index: 0,
  is_locked: false,
} as Chapter

function Wrapper({ children }: { children: ReactNode }) {
  return <I18nextProvider i18n={i18n}>{children}</I18nextProvider>
}

function renderList(move?: ChapterMove) {
  return render(
    <ChapterList
      chapters={[LESSON]}
      onDragEnd={vi.fn()}
      onTitleChange={vi.fn()}
      onRename={vi.fn()}
      onToggleLock={vi.fn()}
      onEdit={vi.fn()}
      onDelete={vi.fn()}
      moveFor={move ? () => move : undefined}
    />,
    { wrapper: Wrapper },
  )
}

describe("ChapterRow — the move control", () => {
  it("offers a way out even when the course has no other module to offer", async () => {
    await i18n.changeLanguage("ru")
    // The module editor's shape: nowhere else to file it, but it can still
    // come out and sit in the course. Deciding on ``intoModules`` alone
    // would hide the one move this screen exists to make.
    renderList({ intoModules: [], canUngroup: true, onMove: vi.fn() })

    expect(screen.getByLabelText(/Переместить урок «Кто написал послание»/i)).toBeInTheDocument()
  })

  it("renders nothing when there is neither a way out nor anywhere to go", async () => {
    await i18n.changeLanguage("ru")
    renderList({ intoModules: [], canUngroup: false, onMove: vi.fn() })

    expect(screen.queryByLabelText(/Переместить урок/i)).not.toBeInTheDocument()
  })

  it("renders nothing when the screen offers no move at all", async () => {
    await i18n.changeLanguage("ru")
    renderList()

    expect(screen.queryByLabelText(/Переместить урок/i)).not.toBeInTheDocument()
  })
})
