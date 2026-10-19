import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { I18nextProvider } from "react-i18next"
import { MemoryRouter } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"

import i18n from "@/i18n/config"
import { organizationsService } from "@/services/organizations"
import OrganizationsPage from "../OrganizationsPage"

describe("the organizations list", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru")
    vi.restoreAllMocks()
  })

  it("asks again from a failed load", async () => {
    const list = vi.spyOn(organizationsService, "list").mockRejectedValueOnce(new Error("offline")).mockResolvedValue([])
    render(
      <I18nextProvider i18n={i18n}>
        <MemoryRouter>
          <OrganizationsPage />
        </MemoryRouter>
      </I18nextProvider>,
    )
    expect(await screen.findByRole("alert")).toBeInTheDocument()
    await userEvent.click(screen.getByRole("button", { name: "Повторить" }))
    expect(await screen.findByText(i18n.t("organizations.empty"))).toBeInTheDocument()
    expect(list).toHaveBeenCalledTimes(2)
  })
})
