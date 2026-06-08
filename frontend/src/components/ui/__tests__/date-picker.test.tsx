import type { ReactNode } from "react"
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { I18nextProvider } from "react-i18next"
import { describe, expect, it, vi } from "vitest"

import i18n from "@/i18n/config"
import { DatePicker } from "../date-picker"

function Wrapper({ children }: { children: ReactNode }) {
  return <I18nextProvider i18n={i18n}>{children}</I18nextProvider>
}

function dayCell(text: string) {
  return screen.getAllByRole("button").find((b) => b.textContent === text)
}

describe("DatePicker", () => {
  it("renders the placeholder when no value is set", () => {
    render(<DatePicker value="" onChange={() => {}} />, { wrapper: Wrapper })
    expect(screen.getByText(/pick a date|выберите дату/i)).toBeInTheDocument()
  })

  it("emits YYYY-MM-DD for the picked day", async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<DatePicker value="2026-05-10" onChange={onChange} />, { wrapper: Wrapper })
    await user.click(screen.getByRole("button"))
    const day20 = await waitFor(() => {
      const el = dayCell("20")
      expect(el).toBeDefined()
      return el!
    })
    await user.click(day20)
    expect(onChange).toHaveBeenCalledWith("2026-05-20")
  })

  it("marks the current value's day with aria-pressed", async () => {
    const user = userEvent.setup()
    render(<DatePicker value="2026-05-10" onChange={() => {}} />, { wrapper: Wrapper })
    await user.click(screen.getByRole("button"))
    const day10 = await waitFor(() => {
      const el = dayCell("10")
      expect(el).toBeDefined()
      return el!
    })
    expect(day10).toHaveAttribute("aria-pressed", "true")
  })

  it("navigates to the previous month and picks from it", async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<DatePicker value="2026-05-10" onChange={onChange} />, { wrapper: Wrapper })
    await user.click(screen.getByRole("button"))
    await user.click(await screen.findByRole("button", { name: /previous month|предыдущий месяц/i }))
    const day15 = await waitFor(() => {
      const el = dayCell("15")
      expect(el).toBeDefined()
      return el!
    })
    await user.click(day15)
    expect(onChange).toHaveBeenCalledWith("2026-04-15")
  })

  it("clear emits an empty string", async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<DatePicker value="2026-05-10" onChange={onChange} />, { wrapper: Wrapper })
    await user.click(screen.getByRole("button"))
    await user.click(await screen.findByRole("button", { name: /^(clear|очистить)$/i }))
    expect(onChange).toHaveBeenCalledWith("")
  })
})
