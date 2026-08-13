import type { ReactNode } from "react"
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { I18nextProvider } from "react-i18next"
import { beforeEach, describe, expect, it, vi } from "vitest"
import i18n from "@/i18n/config"
import { rubricsService } from "@/services/rubrics"
import { RubricEditor } from "../RubricEditor"
import type { Rubric } from "@/types"

const MADE: Rubric = {
  id: "r-1",
  course_id: "c-1",
  title: "Рубрика эссе",
  max_score: 30,
  criteria: [
    {
      id: "cr-1",
      title: "Опора на текст",
      description: null,
      order_index: 0,
      levels: [
        { id: "l-1", label: "слабо", points: 0, description: null, order_index: 0 },
        { id: "l-2", label: "уверенно", points: 10, description: null, order_index: 1 },
      ],
    },
  ],
}

function Wrapper({ children }: { children: ReactNode }) {
  return <I18nextProvider i18n={i18n}>{children}</I18nextProvider>
}

function show() {
  return render(<RubricEditor courseId="c-1" assignmentId="a-1" />, { wrapper: Wrapper })
}

describe("RubricEditor", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru")
    vi.restoreAllMocks()
    vi.spyOn(rubricsService, "listForCourse").mockResolvedValue([])
  })

  it("says what a rubric is for before asking anybody to build one", async () => {
    show()

    // A teacher who has never used one needs the argument, not a form. The
    // argument is consistency, not speed.
    expect(await screen.findByText(/одинаковая мерка на двадцатой работе/)).toBeInTheDocument()
  })

  it("opens with named criteria and levels rather than an empty grid", async () => {
    show()
    await userEvent.click(await screen.findByRole("button", { name: /Создать рубрику/ }))

    // A blank table with a Save button is where this feature dies.
    expect(screen.getAllByPlaceholderText(/Что оцениваем/)).toHaveLength(3)
    expect(screen.getAllByDisplayValue("уверенно")).toHaveLength(3)
  })

  it("creates and attaches in one action", async () => {
    const create = vi.spyOn(rubricsService, "create").mockResolvedValue(MADE)
    const attach = vi.spyOn(rubricsService, "attach").mockResolvedValue(MADE)
    show()
    await userEvent.click(await screen.findByRole("button", { name: /Создать рубрику/ }))
    await userEvent.type(screen.getAllByPlaceholderText(/Что оцениваем/)[0]!, "Опора на текст")
    await userEvent.click(screen.getByRole("button", { name: /Сохранить и применить/ }))

    // A rubric created and not attached is a rubric nobody marks with.
    await waitFor(() => expect(attach).toHaveBeenCalledWith("a-1", "r-1"))
    expect(create.mock.calls[0]?.[0].criteria).toHaveLength(1)
  })

  it("drops criteria the teacher left unnamed", async () => {
    const create = vi.spyOn(rubricsService, "create").mockResolvedValue(MADE)
    vi.spyOn(rubricsService, "attach").mockResolvedValue(MADE)
    show()
    await userEvent.click(await screen.findByRole("button", { name: /Создать рубрику/ }))
    await userEvent.type(screen.getAllByPlaceholderText(/Что оцениваем/)[0]!, "Только один")
    await userEvent.click(screen.getByRole("button", { name: /Сохранить и применить/ }))

    // Three arrive by default; two stayed blank and must not become criteria
    // called "" that a student later sees on their grade.
    await waitFor(() => expect(create).toHaveBeenCalled())
    expect(create.mock.calls[0]?.[0].criteria).toHaveLength(1)
  })

  it("refuses to save a rubric with nothing named", async () => {
    const create = vi.spyOn(rubricsService, "create")
    show()
    await userEvent.click(await screen.findByRole("button", { name: /Создать рубрику/ }))
    await userEvent.click(screen.getByRole("button", { name: /Сохранить и применить/ }))

    expect(create).not.toHaveBeenCalled()
  })

  it("offers the course's existing rubrics before offering to retype one", async () => {
    vi.spyOn(rubricsService, "listForCourse").mockResolvedValue([MADE])
    show()

    // «Наша стандартная рубрика эссе» is the thing a school actually wants,
    // and it is why rubrics are scoped to the course.
    expect(await screen.findByRole("button", { name: /Рубрика эссе/ })).toBeInTheDocument()
  })
})
