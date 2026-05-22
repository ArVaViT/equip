import type { ReactNode } from "react"
import { render, screen, within } from "@testing-library/react"
import { I18nextProvider } from "react-i18next"
import { describe, expect, it } from "vitest"
import i18n from "@/i18n/config"
import { StreakCard } from "../StreakCard"

function Wrapper({ children }: { children: ReactNode }) {
  return <I18nextProvider i18n={i18n}>{children}</I18nextProvider>
}

describe("StreakCard", () => {
  it("renders the eyebrow + title + 7 day cells", () => {
    render(<StreakCard />, { wrapper: Wrapper })
    // Title (whichever locale is active in tests)
    const heading = screen.getByRole("heading")
    expect(heading.textContent?.trim().length).toBeGreaterThan(0)

    // 7 day cells in the week strip
    const group = screen.getByRole("group")
    const labels = within(group).getAllByText(
      /^(Mon|Tue|Wed|Thu|Fri|Sat|Sun|Пн|Вт|Ср|Чт|Пт|Сб|Вс)$/i,
    )
    expect(labels).toHaveLength(7)
  })

  it("renders the coming-soon hint so the card can't be mistaken for finished", () => {
    render(<StreakCard />, { wrapper: Wrapper })
    // Match by the trailing-em-dash + word fragment shared across locales.
    expect(screen.getByText(/placeholder|плейсхолдер/i)).toBeInTheDocument()
  })

  it("renders three preview tasks (question / chapter / verse) as the example list", () => {
    render(<StreakCard />, { wrapper: Wrapper })
    // The three example tasks share the unordered-list container.
    const items = screen.getAllByRole("listitem")
    expect(items).toHaveLength(3)
  })
})
