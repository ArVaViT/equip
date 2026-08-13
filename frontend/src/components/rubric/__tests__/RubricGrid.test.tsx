import type { ReactNode } from "react"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { I18nextProvider } from "react-i18next"
import { beforeEach, describe, expect, it, vi } from "vitest"
import i18n from "@/i18n/config"
import { RubricGrid } from "../RubricGrid"
import type { Rubric, RubricMark } from "@/types"

const RUBRIC: Rubric = {
  id: "r1",
  course_id: "c1",
  title: "Эссе",
  max_score: 18,
  criteria: [
    {
      id: "cr1",
      title: "Опора на текст",
      description: null,
      order_index: 0,
      levels: [
        { id: "l1", label: "нет", points: 0, description: null, order_index: 0 },
        { id: "l2", label: "частично", points: 5, description: null, order_index: 1 },
        { id: "l3", label: "уверенно", points: 10, description: null, order_index: 2 },
      ],
    },
    {
      id: "cr2",
      title: "Ясность",
      description: null,
      order_index: 1,
      levels: [
        { id: "l4", label: "слабо", points: 0, description: null, order_index: 0 },
        { id: "l5", label: "хорошо", points: 8, description: null, order_index: 1 },
      ],
    },
  ],
}

function Wrapper({ children }: { children: ReactNode }) {
  return <I18nextProvider i18n={i18n}>{children}</I18nextProvider>
}

function show(marks: RubricMark[], onChoose?: (c: string, l: string) => void) {
  return render(<RubricGrid rubric={RUBRIC} marks={marks} onChoose={onChoose} />, { wrapper: Wrapper })
}

const mark = (criterion_id: string, level_id: string, points: number): RubricMark => ({
  criterion_id,
  level_id,
  points,
  comment: null,
})

describe("RubricGrid", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru")
  })

  it("totals out of the rubric, not out of what has been marked", () => {
    show([mark("cr1", "l3", 10)], vi.fn())

    // One criterion of two marked. Totalling out of the marks would show a
    // teacher — and then a student — a perfect score on a half-read essay.
    expect(screen.getByText("10 / 18")).toBeInTheDocument()
  })

  it("says plainly that an incomplete grid is not a grade", () => {
    show([mark("cr1", "l3", 10)], vi.fn())

    expect(screen.getByText(/оценка не выставляется/)).toBeInTheDocument()
  })

  it("stops saying it once every criterion has a level", () => {
    show([mark("cr1", "l3", 10), mark("cr2", "l5", 8)], vi.fn())

    expect(screen.getByText("18 / 18")).toBeInTheDocument()
    expect(screen.queryByText(/оценка не выставляется/)).not.toBeInTheDocument()
  })

  it("reports the level, never the points", async () => {
    const onChoose = vi.fn()
    show([], onChoose)

    await userEvent.click(screen.getByRole("button", { name: /частично/ }))

    // The client sends which rung was chosen and the server reads the number
    // from it. A mark that carries its own number is a number the server has
    // to trust.
    expect(onChoose).toHaveBeenCalledWith("cr1", "l2")
  })

  it("marks the chosen level for a screen reader, not only in colour", () => {
    show([mark("cr1", "l3", 10)], vi.fn())

    expect(screen.getByRole("button", { name: /уверенно/ })).toHaveAttribute("aria-pressed", "true")
    expect(screen.getByRole("button", { name: /частично/ })).toHaveAttribute("aria-pressed", "false")
  })

  it("is read-only for the student, and still shows the levels they did not get", () => {
    show([mark("cr1", "l2", 5)])

    // The levels above theirs are the part that answers «а что нужно было
    // сделать», so a student's grid renders the same buttons rather than a
    // stripped-down summary.
    expect(screen.getByRole("button", { name: /уверенно/ })).toBeDisabled()
    expect(screen.getByRole("button", { name: /частично/ })).toHaveAttribute("aria-pressed", "true")
  })
})
