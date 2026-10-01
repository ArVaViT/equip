/**
 * The paste box as a teacher meets it, in Russian: the preview counts the
 * questions, names the one that is not a question yet, and "Add" hands only
 * the good ones to the editor.
 */

import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { I18nextProvider } from "react-i18next"
import { afterAll, beforeAll, describe, expect, it, vi } from "vitest"

import i18n from "@/i18n/config"
import { ImportQuestionsDialog } from "../editor/ImportQuestionsDialog"

const PASTED = `Кто написал книгу Деяний?
А) Пётр
Б) Лука
Ответ: Б

Сколько было апостолов?
А) 7
Б) 12

Где обратился Савл?
А) По дороге в Дамаск
Б) В Иерусалиме *`

describe("ImportQuestionsDialog", () => {
  let before: string
  beforeAll(async () => {
    before = i18n.language
    await i18n.changeLanguage("ru")
  })
  afterAll(async () => {
    await i18n.changeLanguage(before)
  })

  it("previews what will be added and hands over only the questions", async () => {
    const user = userEvent.setup()
    const onImport = vi.fn()
    render(
      <I18nextProvider i18n={i18n}>
        <ImportQuestionsDialog onImport={onImport} />
      </I18nextProvider>,
    )
    await user.click(screen.getByRole("button", { name: "Вставить из текста" }))
    const box = screen.getByRole("textbox", { name: "Вставить вопросы из текста" })
    // `paste`, not `type`: userEvent reads `{` and `[` as key names.
    box.focus()
    await user.paste(PASTED)

    expect(screen.getByText("Найдено 2 вопроса")).toBeInTheDocument()
    expect(screen.getByText(/Сколько было апостолов\?.*не отмечен правильный ответ/)).toBeInTheDocument()

    await user.click(screen.getByRole("button", { name: "Добавить 2 вопроса" }))
    expect(onImport).toHaveBeenCalledTimes(1)
    const added = onImport.mock.calls[0]![0] as { question_text: string; options: { is_correct: boolean }[] }[]
    expect(added.map((q) => q.question_text)).toEqual(["Кто написал книгу Деяний?", "Где обратился Савл?"])
    expect(added.map((q) => q.options.findIndex((o) => o.is_correct))).toEqual([1, 1])
  })
})
