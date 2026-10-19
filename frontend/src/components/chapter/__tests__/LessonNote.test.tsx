/** The note under a lesson: shown when there is one, saved on blur and when the lesson is left. */
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { I18nextProvider } from "react-i18next"
import { MemoryRouter } from "react-router-dom"
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest"

import i18n from "@/i18n/config"
import api from "@/services/api"
import { notesService } from "@/services/notes"
import { noteDraftKey } from "@/lib/storageKeys"
import { LessonNote } from "../LessonNote"

vi.mock("@/context/useAuth", () => ({ useAuth: () => ({ user: { id: "u1" } }) }))

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
  beforeEach(() => {
    window.localStorage.clear()
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
    await waitFor(() => expect(save).toHaveBeenCalledWith("c1", "Спросить про Пятидесятницу"))
  })

  it("offers no box over a note that failed to load, only a retry", async () => {
    const user = userEvent.setup()
    const get = vi.spyOn(notesService, "get").mockRejectedValueOnce(new Error("offline"))
    const save = vi.spyOn(notesService, "save")
    show()
    expect(await screen.findByText("Не удалось загрузить заметку к уроку.")).toBeInTheDocument()
    expect(screen.queryByRole("textbox")).toBeNull()
    get.mockResolvedValueOnce({ chapter_id: "c1", body: "Существующая", updated_at: null })
    await user.click(screen.getByRole("button", { name: "Повторить" }))
    expect(await screen.findByRole("textbox")).toHaveValue("Существующая")
    expect(save).not.toHaveBeenCalled()
  })

  it("sends one save at a time, and never the same note twice", async () => {
    const user = userEvent.setup()
    vi.spyOn(notesService, "get").mockResolvedValue({ chapter_id: "c1", body: null, updated_at: null })
    let release: () => void = () => {}
    const save = vi.spyOn(notesService, "save").mockImplementation(
      (_id, body) => new Promise((resolve) => (release = () => resolve({ chapter_id: "c1", body, updated_at: null }))),
    )
    const view = show()
    await user.click(await screen.findByRole("button", { name: "Добавить заметку к уроку" }))
    await user.type(screen.getByRole("textbox"), "hello")
    await user.tab() // blur: a save starts and hangs
    view.unmount() // leaving: queued behind it
    expect(save).toHaveBeenCalledTimes(1)
    release()
    await new Promise((r) => setTimeout(r, 0))
    expect(save).toHaveBeenCalledTimes(1)
  })

  it("coming straight back reads the note after every save from leaving has landed", async () => {
    const user = userEvent.setup()
    let server = ""
    const releases: (() => void)[] = []
    vi.spyOn(api, "put").mockImplementation(
      (_url, body) =>
        new Promise((resolve) =>
          releases.push(() => {
            server = (body as { body: string }).body
            resolve({ data: { chapter_id: "c1", body: server, updated_at: null } })
          }),
        ),
    )
    vi.spyOn(api, "get").mockImplementation(async () => ({ data: { chapter_id: "c1", body: server || null, updated_at: null } }))

    const first = show()
    await user.click(await screen.findByRole("button", { name: "Добавить заметку к уроку" }))
    await user.type(screen.getByRole("textbox"), "A")
    await user.tab() // save "A" starts and hangs
    await user.click(screen.getByRole("textbox"))
    await user.type(screen.getByRole("textbox"), "B")
    first.unmount() // save "AB" is handed over at once, behind "A"

    show() // straight back
    await new Promise((r) => setTimeout(r, 0))
    releases.shift()!()
    await new Promise((r) => setTimeout(r, 0))
    releases.shift()!()
    expect(await screen.findByRole("textbox")).toHaveValue("AB")
  })

  it("puts back a note that the save on leaving could not deliver, and sends it again", async () => {
    const user = userEvent.setup()
    vi.spyOn(notesService, "get").mockResolvedValue({ chapter_id: "c1", body: null, updated_at: null })
    const save = vi
      .spyOn(notesService, "save")
      .mockRejectedValueOnce(new Error("offline"))
      .mockResolvedValue({ chapter_id: "c1", body: "Спросить про Пятидесятницу", updated_at: null })
    const first = show()
    await user.click(await screen.findByRole("button", { name: "Добавить заметку к уроку" }))
    await user.type(screen.getByRole("textbox"), "Спросить про Пятидесятницу")
    first.unmount() // the save goes out and is refused; nothing on screen to say so
    await waitFor(() => expect(save).toHaveBeenCalledTimes(1))
    expect(JSON.parse(window.localStorage.getItem(noteDraftKey("u1", "c1")) ?? "null")).toEqual({
      text: "Спросить про Пятидесятницу",
      base: "",
    })

    show() // the next visit
    expect(await screen.findByRole("textbox")).toHaveValue("Спросить про Пятидесятницу")
    await waitFor(() => expect(save).toHaveBeenCalledTimes(2), { timeout: 3000 })
    expect(save).toHaveBeenLastCalledWith("c1", "Спросить про Пятидесятницу")
    await waitFor(() => expect(window.localStorage.getItem(noteDraftKey("u1", "c1"))).toBeNull())
  })

  it("leaves a note edited elsewhere since the draft alone: the saved edit wins over the unsaved one", async () => {
    // Typed here over «Деян 2:42», never delivered; then edited on another
    // device. Sent anyway, the draft would have written over that edit.
    window.localStorage.setItem(
      noteDraftKey("u1", "c1"),
      JSON.stringify({ text: "Деян 2:42 — черновик с телефона", base: "Деян 2:42" }),
    )
    vi.spyOn(notesService, "get").mockResolvedValue({ chapter_id: "c1", body: "Деян 2:42 — правка с ноутбука", updated_at: null })
    const save = vi.spyOn(notesService, "save")
    const view = show()
    expect(await screen.findByRole("textbox")).toHaveValue("Деян 2:42 — правка с ноутбука")
    expect(window.localStorage.getItem(noteDraftKey("u1", "c1"))).toBeNull()
    view.unmount()
    expect(save).not.toHaveBeenCalled()
  })

  it("does not keep a note the server already holds as a draft", async () => {
    vi.spyOn(notesService, "get").mockResolvedValue({ chapter_id: "c1", body: "Деян 2:42", updated_at: null })
    const save = vi.spyOn(notesService, "save")
    const view = show()
    expect(await screen.findByRole("textbox")).toHaveValue("Деян 2:42")
    view.unmount()
    expect(window.localStorage.getItem(noteDraftKey("u1", "c1"))).toBeNull()
    expect(save).not.toHaveBeenCalled()
  })
})
