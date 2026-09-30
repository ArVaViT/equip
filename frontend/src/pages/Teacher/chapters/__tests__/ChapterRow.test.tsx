import type { ReactNode } from "react"
import { fireEvent, render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { DragDropContext, Droppable } from "@hello-pangea/dnd"
import { I18nextProvider } from "react-i18next"
import { describe, expect, it, vi } from "vitest"
import i18n from "@/i18n/config"
import type { Chapter } from "@/types"
import { ChapterRow } from "../ChapterRow"

function List({ children }: { children: ReactNode }) {
  return (
    <I18nextProvider i18n={i18n}>
      <DragDropContext onDragEnd={() => {}}>
        <Droppable droppableId="d">
          {(p) => (
            <div ref={p.innerRef} {...p.droppableProps}>
              {children}
              {p.placeholder}
            </div>
          )}
        </Droppable>
      </DragDropContext>
    </I18nextProvider>
  )
}

const chapter = { id: "ch-1", title: "Урок 1. Введение", chapter_type: "reading", is_locked: false, order_index: 0 } as Chapter

function renderRow() {
  const props = {
    onTitleChange: vi.fn(),
    onRename: vi.fn(),
    onToggleLock: vi.fn(),
    onEdit: vi.fn(),
    onDelete: vi.fn(),
  }
  render(<ChapterRow chapter={chapter} index={0} {...props} />, { wrapper: List })
  return props
}

describe("ChapterRow", () => {
  it("opens the lesson from its name", async () => {
    const props = renderRow()
    await userEvent.click(screen.getByRole("button", { name: "Урок 1. Введение" }))
    expect(props.onEdit).toHaveBeenCalledOnce()
    expect(props.onRename).not.toHaveBeenCalled()
  })

  it("renames from its own button, and Escape leaves the name as it was", async () => {
    await i18n.changeLanguage("ru")
    const props = renderRow()
    await userEvent.click(screen.getByRole("button", { name: /Переименовать урок/ }))
    const input = screen.getByRole("textbox", { name: /Переименовать урок/ })
    expect(input).toHaveFocus()
    fireEvent.keyDown(input, { key: "Escape" })
    expect(props.onRename).not.toHaveBeenCalled()
    expect(screen.getByRole("button", { name: "Урок 1. Введение" })).toBeInTheDocument()
  })
})
