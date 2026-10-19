/** A refused rename goes back to the title before editing began — the row is the one place that still knows it. */
import { useState, type ReactNode } from "react"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { I18nextProvider } from "react-i18next"
import { DragDropContext, Droppable } from "@hello-pangea/dnd"
import { beforeEach, describe, expect, it, vi } from "vitest"

import i18n from "@/i18n/config"
import type { Chapter } from "@/types"
import { ChapterRow } from "../ChapterRow"

function Wrapper({ children }: { children: ReactNode }) {
  return (
    <I18nextProvider i18n={i18n}>
      <DragDropContext onDragEnd={() => undefined}>
        <Droppable droppableId="d">
          {(provided) => (
            <div ref={provided.innerRef} {...provided.droppableProps}>
              {children}
              {provided.placeholder}
            </div>
          )}
        </Droppable>
      </DragDropContext>
    </I18nextProvider>
  )
}

describe("ChapterRow — renaming", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("en")
  })

  it("hands the title before editing along with the typed one", async () => {
    const onRename = vi.fn()
    // As in the outline: every keystroke is written into the course first.
    function Harness() {
      const [title, setTitle] = useState("Pentecost")
      const chapter = { id: "l1", title, chapter_type: "reading", is_locked: false, order_index: 0 } as Chapter
      return (
        <ChapterRow chapter={chapter} index={0} onTitleChange={setTitle} onRename={onRename} onToggleLock={vi.fn()} onEdit={vi.fn()} onDelete={vi.fn()} />
      )
    }
    render(<Harness />, { wrapper: Wrapper })
    await userEvent.click(screen.getByRole("button", { name: /rename/i }))
    await userEvent.type(screen.getByRole("textbox"), " and after")
    await userEvent.tab()

    // The row's chapter.title is the typed text by now; the saved one travels beside it.
    expect(onRename).toHaveBeenCalledWith("Pentecost and after", "Pentecost")
  })
})
