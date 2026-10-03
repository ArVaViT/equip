/**
 * The block as a teacher and a director meet it in Russian: what the course is
 * graded on, who decides, and what happens when the server says no.
 */
import type { ReactNode } from "react"
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { AxiosError } from "axios"
import { I18nextProvider } from "react-i18next"
import { beforeEach, describe, expect, it, vi } from "vitest"

import i18n from "@/i18n/config"
import type { GradingSchemeResponse } from "@/types"
import { GradingScaleCard } from "../GradingScaleCard"

const getGradingScheme = vi.fn()
const updateGradingScheme = vi.fn()
vi.mock("@/services/grades", () => ({
  gradesService: {
    getGradingScheme: (...args: unknown[]) => getGradingScheme(...args),
    updateGradingScheme: (...args: unknown[]) => updateGradingScheme(...args),
  },
}))

const toast = vi.fn()
vi.mock("@/lib/toast", () => ({ toast: (...args: unknown[]) => toast(...args) }))

const LETTER: GradingSchemeResponse = {
  grading_scheme: "letter",
  pass_threshold: "70.00",
  bands: [
    ["90", "A"],
    ["80", "B"],
    ["70", "C"],
    ["60", "D"],
    ["0", "F"],
  ],
}

function equipError(status: number, context: Record<string, unknown>) {
  const err = new AxiosError("request failed")
  err.response = {
    status,
    statusText: "",
    headers: {},
    config: { headers: undefined } as never,
    data: { detail: { code: "validation.failed", message: "hand-set grades exist", context } },
  }
  return err
}

function Wrapper({ children }: { children: ReactNode }) {
  return <I18nextProvider i18n={i18n}>{children}</I18nextProvider>
}

async function show(canChange: boolean, onChanged = vi.fn()) {
  render(<GradingScaleCard courseId="c-1" canChange={canChange} onChanged={onChanged} />, {
    wrapper: Wrapper,
  })
  await screen.findByText("Шкала оценок")
  return onChanged
}

describe("GradingScaleCard", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru")
    getGradingScheme.mockReset().mockResolvedValue(LETTER)
    updateGradingScheme.mockReset()
    toast.mockReset()
  })

  it("shows a teacher the scheme, the pass line and the bands — and no control", async () => {
    await show(false)

    expect(screen.getByText("буквенная · проходной балл 70%")).toBeInTheDocument()
    expect(screen.getByText("A 90–100 · B 80–89 · C 70–79 · D 60–69 · F 0–59")).toBeInTheDocument()
    expect(screen.getByText("Шкалу выбирает директор школы.")).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "Изменить" })).not.toBeInTheDocument()
  })

  it("gives a director the Change button and a dialog with both values", async () => {
    const user = userEvent.setup()
    await show(true)
    // The director is who decides: the card does not tell them to ask one.
    expect(screen.queryByText("Шкалу выбирает директор школы.")).not.toBeInTheDocument()

    await user.click(screen.getByRole("button", { name: "Изменить" }))

    expect(screen.getByRole("dialog", { name: "Как оценивается курс" })).toBeInTheDocument()
    expect(screen.getByLabelText("Проходной балл (%)")).toHaveValue(70)
    expect(screen.getByRole("combobox", { name: "Шкала" })).toHaveTextContent("буквенная")
  })

  it("objects before the round-trip when the pair cannot work", async () => {
    const user = userEvent.setup()
    await show(true)
    await user.click(screen.getByRole("button", { name: "Изменить" }))

    const threshold = screen.getByLabelText("Проходной балл (%)")
    await user.clear(threshold)
    await user.type(threshold, "120")

    expect(screen.getByRole("alert")).toHaveTextContent("Проходной балл — число от 0 до 100.")
    expect(screen.getByRole("button", { name: "Сохранить" })).toBeDisabled()
    expect(updateGradingScheme).not.toHaveBeenCalled()
  })

  it("keeps the dialog open on 409 and says how many hand-set grades stand in the way", async () => {
    const user = userEvent.setup()
    updateGradingScheme.mockRejectedValue(equipError(409, { affected_students: ["s-1", "s-2", "s-3"] }))
    const onChanged = await show(true)
    await user.click(screen.getByRole("button", { name: "Изменить" }))

    await user.click(screen.getByRole("button", { name: "Сохранить" }))

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "В курсе 3 оценки выставлены вручную по прежней шкале. Снимите их или введите заново, потом меняйте шкалу.",
    )
    expect(screen.getByRole("dialog", { name: "Как оценивается курс" })).toBeInTheDocument()
    expect(onChanged).not.toHaveBeenCalled()
    expect(toast).not.toHaveBeenCalled()
  })

  it("closes, refreshes the block and toasts when the change lands", async () => {
    const user = userEvent.setup()
    updateGradingScheme.mockResolvedValue({ ...LETTER, pass_threshold: "60.00" })
    const onChanged = await show(true)
    await user.click(screen.getByRole("button", { name: "Изменить" }))

    const threshold = screen.getByLabelText("Проходной балл (%)")
    await user.clear(threshold)
    await user.type(threshold, "60")
    await user.click(screen.getByRole("button", { name: "Сохранить" }))

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument())
    expect(updateGradingScheme).toHaveBeenCalledWith("c-1", { grading_scheme: "letter", pass_threshold: 60 })
    expect(screen.getByText("буквенная · проходной балл 60%")).toBeInTheDocument()
    expect(onChanged).toHaveBeenCalledTimes(1)
    expect(toast).toHaveBeenCalledWith({ title: "Шкала оценок сохранена", variant: "success" })
  })
})
