/**
 * The dialog as a teacher meets it in Russian: pick who, see how many and
 * their names, and the mail link carries exactly them.
 */
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { I18nextProvider } from "react-i18next"
import { beforeAll, describe, expect, it } from "vitest"

import i18n from "@/i18n/config"
import { WriteToStudents } from "../WriteToStudents"
import type { StudentProgressData } from "../types"

const chapters = (quizPassed: boolean | null) => [
  { id: "r1", title: "Чтение", module_id: "m", chapter_type: "reading", completed: true, completed_by: null, quiz_result: null, assignment_result: null },
  {
    id: "q1",
    title: "Тест 1",
    module_id: "m",
    chapter_type: "quiz",
    completed: false,
    completed_by: null,
    quiz_result: quizPassed === null ? null : { score: 1, max_score: 10, passed: quizPassed },
    assignment_result: null,
  },
]

const STUDENTS = [
  { id: "1", full_name: "Анна", email: "anna@example.com", chapters: chapters(null) },
  { id: "2", full_name: "Борис", email: "boris@example.com", chapters: chapters(false) },
  { id: "3", full_name: "Вера", email: "vera@example.com", chapters: chapters(true) },
] as unknown as StudentProgressData[]

describe("WriteToStudents", () => {
  beforeAll(async () => {
    await i18n.changeLanguage("ru")
  })

  it("lists who will get the note and links their mail to exactly them", async () => {
    const user = userEvent.setup()
    render(
      <I18nextProvider i18n={i18n}>
        <WriteToStudents courseTitle="Деяния" students={STUDENTS} />
      </I18nextProvider>,
    )
    await user.click(screen.getByRole("button", { name: "Написать…" }))
    // Only work is offered, not reading.
    expect(screen.getByRole("combobox")).toHaveDisplayValue("Тест 1")
    expect(screen.getByText("1 студент")).toBeInTheDocument()
    expect(screen.getByText("Анна")).toBeInTheDocument()
    expect(screen.getByRole("link", { name: "Открыть письмо" })).toHaveAttribute(
      "href",
      expect.stringMatching(/^mailto:\?bcc=anna@example\.com&subject=/),
    )

    await user.click(screen.getByRole("radio", { name: "Весь класс" }))
    expect(screen.getByText("3 студента")).toBeInTheDocument()
    expect(screen.queryByRole("combobox")).toBeNull()
  })

  it("offers to copy instead of a mail link too long for some mail programs", async () => {
    const user = userEvent.setup()
    const many = Array.from({ length: 80 }, (_, i) => ({
      ...STUDENTS[0]!,
      id: String(i),
      full_name: `Студент ${i}`,
      email: `student-number-${i}@example.com`,
    }))
    render(
      <I18nextProvider i18n={i18n}>
        <WriteToStudents courseTitle="Деяния" students={many} />
      </I18nextProvider>,
    )
    await user.click(screen.getByRole("button", { name: "Написать…" }))
    expect(screen.queryByRole("link", { name: "Открыть письмо" })).toBeNull()
    expect(screen.getByText(/Адресов слишком много/)).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Скопировать адреса" })).toBeEnabled()
  })
})
