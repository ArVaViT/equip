import type { ReactNode } from "react"
import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { I18nextProvider } from "react-i18next"
import { describe, expect, it, vi } from "vitest"
import i18n from "@/i18n/config"
import { DateRangePicker } from "../date-range-picker"

function Wrapper({ children }: { children: ReactNode }) {
  return <I18nextProvider i18n={i18n}>{children}</I18nextProvider>
}

describe("DateRangePicker", () => {
  it("renders the placeholder when no range is set", () => {
    render(
      <DateRangePicker value={{ from: "", to: "" }} onChange={() => {}} />,
      { wrapper: Wrapper },
    )
    expect(
      screen.getByText(/pick date range|выберите диапазон/i),
    ).toBeInTheDocument()
  })

  it("renders the chosen range in the trigger label", () => {
    render(
      <DateRangePicker
        value={{ from: "2026-05-01", to: "2026-05-15" }}
        onChange={() => {}}
      />,
      { wrapper: Wrapper },
    )
    // Trigger label uses a localised "May 1, 2026 – May 15, 2026" shape;
    // assert the en-dash separator is present rather than chase the
    // locale-specific date format.
    expect(screen.getByRole("button", { name: /–/ })).toBeInTheDocument()
  })

  it("opens the calendar on trigger click and emits onChange when a day is picked", async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(
      <DateRangePicker value={{ from: "", to: "" }} onChange={onChange} />,
      { wrapper: Wrapper },
    )
    await user.click(screen.getByRole("button"))

    // Pick day 15 of the visible month. The calendar always shows the
    // anchor month (today's month when no value), so 15 is always present.
    const day15 = await waitFor(() =>
      screen.getAllByRole("button").find((b) => b.textContent === "15"),
    )
    expect(day15).toBeDefined()
    await user.click(day15!)

    expect(onChange).toHaveBeenCalledTimes(1)
    const arg = onChange.mock.calls[0]?.[0] as { from: string; to: string }
    expect(arg.from).toMatch(/^\d{4}-\d{2}-15$/)
    expect(arg.to).toBe("")
  })

  it("clear button wipes both bounds", async () => {
    const onChange = vi.fn()
    render(
      <DateRangePicker
        value={{ from: "2026-05-01", to: "2026-05-15" }}
        onChange={onChange}
      />,
      { wrapper: Wrapper },
    )
    fireEvent.click(screen.getByRole("button", { name: /–/ }))

    const clearBtn = await screen.findByRole("button", {
      name: /^(clear|очистить)$/i,
    })
    fireEvent.click(clearBtn)

    expect(onChange).toHaveBeenCalledWith({ from: "", to: "" })
  })
})
