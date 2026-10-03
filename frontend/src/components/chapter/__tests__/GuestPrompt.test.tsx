import { render, screen } from "@testing-library/react"
import { I18nextProvider } from "react-i18next"
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom"
import { describe, expect, it } from "vitest"
import userEvent from "@testing-library/user-event"

import i18n from "@/i18n/config"
import { GuestPrompt, LockedBlock } from "../GuestPrompt"

function Where() {
  const loc = useLocation()
  return <p data-testid="where">{`${loc.pathname}|${JSON.stringify(loc.state)}`}</p>
}

function renderAt(variant: "finish" | "wall") {
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
  it("brings a new account back to the very lesson it left, not to the course page", async () => {
    renderAt("wall")
    await userEvent.click(screen.getByRole("link", { name: i18n.t("guest.register") }))
    expect(screen.getByTestId("where").textContent).toBe('/register|{"from":"/courses/c1/chapters/ch2"}')
  })

  it("and the same for signing in", async () => {
    renderAt("finish")
    await userEvent.click(screen.getByRole("link", { name: i18n.t("guest.signIn") }))
    expect(screen.getByTestId("where").textContent).toBe('/login|{"from":"/courses/c1/chapters/ch2"}')
  })

  it("inside the lesson is one quiet line with no buttons", () => {
    render(
      <I18nextProvider i18n={i18n}>
        <LockedBlock />
      </I18nextProvider>,
    )
    expect(screen.queryByRole("link")).toBeNull()
    expect(screen.getByText(i18n.t("guest.block.title"))).toBeInTheDocument()
  })
})
