import type { ReactNode } from "react"
import { render, screen } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { I18nextProvider } from "react-i18next"
import { describe, expect, it } from "vitest"
import i18n from "@/i18n/config"
import type { User } from "@/types"
import { MobileTabBar } from "../MobileTabBar"

const user = { id: "u-1", role: "student", full_name: "Мария", avatar_url: null } as unknown as User

function at(path: string) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <I18nextProvider i18n={i18n}>
        <MemoryRouter initialEntries={[path]}>{children}</MemoryRouter>
      </I18nextProvider>
    )
  }
}

describe("MobileTabBar", () => {
  it("offers the student four places and marks the one they are in", () => {
    render(<MobileTabBar user={user} isTeacher={false} />, { wrapper: at("/courses/c-1/chapters/x") })
    const links = screen.getAllByRole("link")
    expect(links.map((a) => a.getAttribute("href"))).toEqual(["/", "/courses", "/calendar", "/profile"])
    expect(screen.getByRole("link", { name: /Courses/ })).toHaveAttribute("aria-current", "page")
    expect(screen.getByRole("link", { name: /Home/ })).not.toHaveAttribute("aria-current")
  })

  it("adds teaching for a teacher", () => {
    render(<MobileTabBar user={user} isTeacher />, { wrapper: at("/teacher/courses/c-1") })
    expect(screen.getByRole("link", { name: /Teaching/ })).toHaveAttribute("aria-current", "page")
  })
})
