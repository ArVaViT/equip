/** The only way to a member's closed courses; a failed read must not look like «no institute». */
import type { ReactNode } from "react"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { I18nextProvider } from "react-i18next"
import { MemoryRouter } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"

import i18n from "@/i18n/config"
import { organizationsService } from "@/services/organizations"
import { MyOrganizationsCourses } from "../MyOrganizationsCourses"
import { useMyOrganizationsBlocks } from "../useMyOrganizationsBlocks"

/** The page's wiring: the hook reads, the component shows. */
function Harness({ userId }: { userId: string }) {
  const organizations = useMyOrganizationsBlocks(userId)
  return <MyOrganizationsCourses {...organizations} progress={new Map()} />
}

function Wrapper({ children }: { children: ReactNode }) {
  return (
    <I18nextProvider i18n={i18n}>
      <MemoryRouter>{children}</MemoryRouter>
    </I18nextProvider>
  )
}

describe("MyOrganizationsCourses", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("en")
    vi.restoreAllMocks()
  })

  it("says the read failed and asks again, instead of showing only the public catalogue", async () => {
    const mine = vi
      .spyOn(organizationsService, "mine")
      .mockRejectedValueOnce(new Error("offline"))
      .mockResolvedValue([
        {
          organization_id: "o1",
          organization_slug: "ucoat",
          organization_name: "UCOAT",
          role: "student",
          courses: [{ id: "k1", title: "Acts", access_mode: "institute" }],
        } as never,
      ])
    render(<Harness userId="u1" />, { wrapper: Wrapper })

    expect(await screen.findByRole("alert")).toBeInTheDocument()
    await userEvent.click(screen.getByRole("button", { name: "Try again" }))

    expect(await screen.findByRole("heading", { name: "UCOAT" })).toBeInTheDocument()
    expect(mine).toHaveBeenCalledTimes(2)
  })
})
