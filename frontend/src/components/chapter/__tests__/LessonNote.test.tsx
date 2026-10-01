/** The note under a lesson: shown when there is one, saved on blur and when the lesson is left. */
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { I18nextProvider } from "react-i18next"
import { MemoryRouter } from "react-router-dom"
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest"

import i18n from "@/i18n/config"
import { notesService } from "@/services/notes"
import { LessonNote } from "../LessonNote"

function show(chapterId = "c1") {
  return render(
    <I18nextProvider i18n={i18n}>
      <MemoryRouter>
        <LessonNote chapterId={chapterId} />
      </MemoryRouter>
    </I18nextProvider>,
  )
}

describe("LessonNote", () => {
  beforeAll(async () => {
    await i18n.changeLanguage("ru")
  })
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it("opens with the note already written, and saves an edit on blur", async () => {
    const user = userEvent.setup()
    vi.spyOn(notesService, "get").mockResolvedValue({ chapter_id: "c1", body: "Деян 2:42", updated_at: null })
    const save = vi.spyOn(notesService, "save").mockResolvedValue({ chapter_id: "c1", body: "Деян 2:42 — четыре признака", updated_at: null })
    show()
    const box = await screen.findByRole("textbox", { name: "Мои заметки к уроку" })
    expect(box).toHaveValue("Деян 2:42")
    await user.type(box, " — четыре признака")
    await user.tab()
    await waitFor(() => expect(save).toHaveBeenCalledWith("c1", "Деян 2:42 — четыре признака"))
    expect(await screen.findByText("Сохранено")).toBeInTheDocument()
  })

  it("is one line until opened, and keeps what was typed when the lesson is left", async () => {
    const user = userEvent.setup()
    vi.spyOn(notesService, "get").mockResolvedValue({ chapter_id: "c1", body: null, updated_at: null })
    const save = vi.spyOn(notesService, "save").mockResolvedValue({ chapter_id: "c1", body: "x", updated_at: null })
    const view = show()
    await user.click(await screen.findByRole("button", { name: "Добавить заметку к уроку" }))
    const box = screen.getByRole("textbox")
    expect(box).toHaveFocus()
    await user.type(box, "Спросить про Пятидесятницу")
    view.unmount()
    expect(save).toHaveBeenCalledWith("c1", "Спросить про Пятидесятницу")
  })
})
