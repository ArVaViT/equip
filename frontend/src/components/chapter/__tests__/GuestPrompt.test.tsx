import { render, screen } from "@testing-library/react"
import { I18nextProvider } from "react-i18next"
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom"
import { describe, expect, it } from "vitest"
import userEvent from "@testing-library/user-event"

import i18n from "@/i18n/config"
import { GuestPrompt } from "../GuestPrompt"

function Where() {
  const loc = useLocation()
  return <p data-testid="where">{`${loc.pathname}|${JSON.stringify(loc.state)}`}</p>
}

function renderAt(variant: "finish" | "wall" | "block") {
  render(
    <I18nextProvider i18n={i18n}>
      <MemoryRouter initialEntries={["/courses/c1/chapters/ch2"]}>
        <Routes>
          <Route path="/courses/:courseId/chapters/:chapterId" element={<GuestPrompt variant={variant} />} />
          <Route path="*" element={<Where />} />
        </Routes>
      </MemoryRouter>
    </I18nextProvider>,
  )
}

describe("GuestPrompt", () => {
  it("sends a new account back to the course page, where enrolling is", async () => {
    renderAt("wall")
    await userEvent.click(screen.getByRole("link", { name: i18n.t("guest.register") }))
    expect(screen.getByTestId("where").textContent).toBe('/register|{"from":"/courses/c1"}')
  })

  it("inside the lesson is one quiet line with no buttons", () => {
    renderAt("block")
    expect(screen.queryByRole("link")).toBeNull()
    expect(screen.getByText(i18n.t("guest.block.title"))).toBeInTheDocument()
  })
})
