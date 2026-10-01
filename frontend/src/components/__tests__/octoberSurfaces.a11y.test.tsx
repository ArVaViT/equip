/**
 * axe over the surfaces added on 2026-10-01, each in its opened state — a
 * dialog or popover is where a missing label hides, and a closed one shows
 * axe nothing.
 */
import type { ReactNode } from "react"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { I18nextProvider } from "react-i18next"
import { MemoryRouter } from "react-router-dom"
import { beforeAll, describe, expect, it, vi } from "vitest"

import i18n from "@/i18n/config"
import { axe } from "@/test/a11y"
import { AuthContext } from "@/context/auth-context"
import { CommentLibrary } from "@/components/grading/CommentLibrary"
import { ReadingControls } from "@/components/chapter/ReadingControls"
import { VerseCard } from "@/components/chapter/VerseCard"
import { LessonNote } from "@/components/chapter/LessonNote"
import MyNotesPage from "@/pages/Notes/MyNotesPage"
import { notesService } from "@/services/notes"
import { WeeklyReview } from "@/components/review/WeeklyReview"
import { reviewService } from "@/services/review"
import { ImportQuestionsDialog } from "@/components/quiz/editor/ImportQuestionsDialog"
import { AddToCalendarButton } from "@/components/calendar/AddToCalendarButton"
import TranscriptPage from "@/pages/Certificates/TranscriptPage"
import { coursesService } from "@/services/courses"
import { MyDataSetting } from "@/pages/Profile/MyDataSetting"
import { WriteToStudents } from "@/pages/Teacher/gradebook/WriteToStudents"
import type { StudentProgressData } from "@/pages/Teacher/gradebook/types"

function wrap(node: ReactNode) {
  return render(
    <I18nextProvider i18n={i18n}>
      <MemoryRouter>{node}</MemoryRouter>
    </I18nextProvider>,
  )
}

describe("today's surfaces have no axe violations", () => {
  beforeAll(async () => {
    await i18n.changeLanguage("ru")
  })

  it("quiz import, opened with a pasted test", async () => {
    const user = userEvent.setup()
    wrap(<ImportQuestionsDialog onImport={vi.fn()} />)
    await user.click(screen.getByRole("button", { name: "Вставить из текста" }))
    screen.getByRole("textbox").focus()
    await user.paste("Кто?\nА) Пётр\nБ) Лука\nОтвет: Б\n\nБез ответа\nА) x\nБ) y")
    expect(await axe(document.body)).toHaveNoViolations()
  })

  it("write to students, opened", async () => {
    const user = userEvent.setup()
    const students = [
      {
        id: "1",
        full_name: "Анна",
        email: "anna@example.com",
        chapters: [{ id: "q", title: "Тест", module_id: "m", chapter_type: "quiz", completed: false, completed_by: null, quiz_result: null, assignment_result: null }],
      },
    ] as unknown as StudentProgressData[]
    wrap(<WriteToStudents courseTitle="Деяния" students={students} />)
    await user.click(screen.getByRole("button", { name: "Написать…" }))
    expect(await axe(document.body)).toHaveNoViolations()
  })

  it("the verse card", async () => {
    const anchor = document.createElement("button")
    anchor.textContent = "Ин 3:16"
    document.body.append(anchor)
    wrap(
      <VerseCard
        anchor={anchor}
        passage={{ written: "Ин 3:16", ref: "john 3:16", text: "Ибо так возлюбил Бог мир…", edition: "nrt" }}
        onClose={vi.fn()}
      />,
    )
    expect(await axe(document.body)).toHaveNoViolations()
    anchor.remove()
  })

  it("reading controls, opened", async () => {
    const user = userEvent.setup()
    wrap(<ReadingControls prefs={{ size: "normal", easy: false } as never} onChange={vi.fn()} />)
    await user.click(screen.getByRole("button"))
    expect(await axe(document.body)).toHaveNoViolations()
  })

  it("my data", async () => {
    const { container } = wrap(<MyDataSetting />)
    expect(await axe(container)).toHaveNoViolations()
  })

  it("the comment library, opened", async () => {
    const user = userEvent.setup()
    const auth = { user: { id: "t", comment_library: ["Укажите стих, а не только главу."] }, applyUser: vi.fn() }
    wrap(
      <AuthContext.Provider value={auth as never}>
        <CommentLibrary current="Хорошо" onInsert={vi.fn()} />
      </AuthContext.Provider>,
    )
    await user.click(screen.getByRole("button", { name: "Мои замечания (1)" }))
    expect(await axe(document.body)).toHaveNoViolations()
  })

  it("add to calendar", async () => {
    const event = { id: "e", title: "Занятие", starts_at: "2026-10-05T17:00:00Z", ends_at: "2026-10-05T18:00:00Z" }
    const { container } = wrap(<AddToCalendarButton event={event as never} />)
    expect(await axe(container)).toHaveNoViolations()
  })

  it("the transcript", async () => {
    vi.spyOn(coursesService, "getMyCertificates").mockResolvedValue([
      {
        id: "c",
        status: "approved",
        student_name: "Anna",
        course_title: "Acts",
        issued_at: "2026-03-01T10:00:00Z",
        certificate_number: "EQ-1",
      } as never,
    ])
    const { container } = wrap(
      <AuthContext.Provider value={{ user: { full_name: "Anna" } } as never}>
        <TranscriptPage />
      </AuthContext.Provider>,
    )
    await screen.findByRole("heading", { name: "Anna" })
    expect(await axe(container)).toHaveNoViolations()
  })

  it("the lesson note, open", async () => {
    vi.spyOn(notesService, "get").mockResolvedValue({ chapter_id: "c", body: "Заметка", updated_at: null })
    const { container } = wrap(<LessonNote chapterId="c" />)
    await screen.findByRole("textbox")
    expect(await axe(container)).toHaveNoViolations()
  })

  it("my notes", async () => {
    vi.spyOn(notesService, "mine").mockResolvedValue([
      {
        chapter_id: "c",
        chapter_title: "Пятидесятница",
        module_id: "m",
        module_title: "Начало",
        course_id: "k",
        course_title: "Деяния",
        body: "Заметка",
        updated_at: "2026-10-01T10:00:00Z",
        available: true,
      },
    ])
    const { container } = wrap(<MyNotesPage />)
    await screen.findByText("Пятидесятница")
    expect(await axe(container)).toHaveNoViolations()
  })

  it("the week's review, answered", async () => {
    const user = userEvent.setup()
    vi.spyOn(reviewService, "forCourse").mockResolvedValue([
      { id: "q", question_text: "Кто?", options: [{ id: "a", option_text: "Пётр" }, { id: "b", option_text: "Павел" }] },
    ])
    vi.spyOn(reviewService, "check").mockResolvedValue({ correct: true, correct_option_id: "a" })
    const { container } = wrap(<WeeklyReview courseId="k" />)
    await user.click(await screen.findByRole("button", { name: "Начать" }))
    await user.click(screen.getByRole("button", { name: "Пётр" }))
    await screen.findByText("Верно")
    expect(await axe(container)).toHaveNoViolations()
  })
})
