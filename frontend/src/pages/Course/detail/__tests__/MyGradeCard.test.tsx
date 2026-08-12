import type { ReactNode } from "react"
import { render, screen } from "@testing-library/react"
import { I18nextProvider } from "react-i18next"
import { MemoryRouter } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"
import i18n from "@/i18n/config"
import { gradesService } from "@/services/grades"
import { MyGradeCard } from "../MyGradeCard"
import type { MyCourseGrade, MyGradeItem } from "@/types"

function item(over: Partial<MyGradeItem> = {}): MyGradeItem {
  return {
    item_id: "i1",
    chapter_id: "ch1",
    title: "Эссе о благодати",
    kind: "assignment",
    status: "graded",
    score: 90,
    feedback: null,
    ...over,
  }
}

function grade(items: MyGradeItem[]): MyCourseGrade {
  return {
    course_id: "c1",
    grading_scheme: "letter",
    pass_threshold: "70.00",
    progress: 100,
    current_score: 90,
    current_symbol: "A",
    final_score: 90,
    final_symbol: "A",
    scores_differ: false,
    result_state: "graded",
    scores_withheld: false,
    zachet: null,
    official_grade: null,
    comment: null,
    certificate_blockers: [],
    items,
  }
}

function Wrapper({ children }: { children: ReactNode }) {
  return (
    <I18nextProvider i18n={i18n}>
      <MemoryRouter>{children}</MemoryRouter>
    </I18nextProvider>
  )
}

async function show(items: MyGradeItem[]) {
  vi.spyOn(gradesService, "getMyCourseGrade").mockResolvedValue(grade(items))
  render(<MyGradeCard courseId="c1" modules={[]} />, { wrapper: Wrapper })
  return screen.findByText("Эссе о благодати")
}

describe("MyGradeCard — the teacher's words, not just the number", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru")
    vi.restoreAllMocks()
  })

  it("shows what the teacher wrote next to the mark", async () => {
    await show([item({ feedback: "Мысль есть, аргументу нужны тексты." })])

    // The number without the words is the grade without the lesson — and for a
    // school teaching by correspondence the written note is the teaching.
    expect(screen.getByText("Мысль есть, аргументу нужны тексты.")).toBeInTheDocument()
  })

  it("shows it on work handed back, where the score is deliberately absent", async () => {
    await show([
      item({ status: "returned", score: null, feedback: "Добавьте отрывки, на которые опираетесь." }),
    ])

    // «Вернул на доработку» with nothing said about what to change is the one
    // row on this card a student cannot act on.
    expect(screen.getByText("Добавьте отрывки, на которые опираетесь.")).toBeInTheDocument()
  })

  it("renders the row unchanged when there is nothing written", async () => {
    await show([item({ feedback: null })])

    expect(screen.getByText("Эссе о благодати")).toBeInTheDocument()
    expect(screen.getByText("90%")).toBeInTheDocument()
  })
})
