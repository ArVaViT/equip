/**
 * The organizations tab says what a status does, asks before suspending,
 * and tells staff whether an organization is on the public showcase.
 *
 * Until 2026-10-03 the status select saved on change with no explanation,
 * and a verified school missing from `/organizations` left staff guessing
 * which of the three conditions it failed.
 */
import type { ReactNode } from "react"
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { I18nextProvider } from "react-i18next"
import { MemoryRouter } from "react-router-dom"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { ConfirmProvider } from "@/components/ui/alert-dialog"
import i18n from "@/i18n/config"
import { organizationsService, type AdminOrganization } from "@/services/organizations"
import { OrganizationsTab } from "../OrganizationsTab"

const org = (over: Partial<AdminOrganization> = {}): AdminOrganization => ({
  id: "o1", slug: "ucoat", public_name: "UCOAT", legal_name: null, country: "US", status: "verified",
  verification_basis: null, verified_at: "2026-09-01T00:00:00Z", created_at: "2026-08-30T00:00:00Z",
  member_count: 2, director_emails: ["d@example.com"], published_courses: 3, ...over,
})

function Wrapper({ children }: { children: ReactNode }) {
  return (
    <I18nextProvider i18n={i18n}>
      <MemoryRouter>
        <ConfirmProvider>{children}</ConfirmProvider>
      </MemoryRouter>
    </I18nextProvider>
  )
}

// Radix Select reads pointer capture and scrolls the chosen item into view;
// jsdom has neither.
beforeEach(async () => {
  await i18n.changeLanguage("ru")
  Element.prototype.hasPointerCapture ??= () => false
  Element.prototype.releasePointerCapture ??= () => {}
  Element.prototype.scrollIntoView ??= () => {}
})
afterEach(async () => {
  vi.restoreAllMocks()
  await i18n.changeLanguage("en")
})

describe("the organizations tab", () => {
  it("says whether each organization is on the showcase, and why not", async () => {
    vi.spyOn(organizationsService, "adminList").mockResolvedValue([
      org(),
      org({ id: "o2", slug: "quiet", public_name: "Quiet School", published_courses: 0 }),
      org({ id: "o3", slug: "new", public_name: "New School", status: "approved", director_emails: [], published_courses: 0 }),
    ])
    render(<OrganizationsTab />, { wrapper: Wrapper })
    expect(await screen.findByText("В списке организаций: да")).toBeInTheDocument()
    expect(screen.getByText("В списке организаций: нет — нет опубликованных курсов")).toBeInTheDocument()
    expect(screen.getByText("В списке организаций: нет — не проверена, нет директора, нет опубликованных курсов")).toBeInTheDocument()
  })

  it("explains the statuses once, and every status select points at the explanation", async () => {
    vi.spyOn(organizationsService, "adminList").mockResolvedValue([org(), org({ id: "o2", slug: "b", public_name: "B" })])
    render(<OrganizationsTab />, { wrapper: Wrapper })
    const help = await screen.findByText(/Проверена — видна всем · Приостановлена — страница остаётся, курсы скрыты, сертификаты действительны/)
    for (const select of screen.getAllByRole("combobox", { name: "Статус" })) {
      expect(select).toHaveAttribute("aria-describedby", help.id)
    }
  })

  it("asks before suspending, and saves nothing when the answer is no", async () => {
    vi.spyOn(organizationsService, "adminList").mockResolvedValue([org()])
    const update = vi.spyOn(organizationsService, "adminUpdate").mockResolvedValue(org({ status: "suspended" }))
    const user = userEvent.setup()
    render(<OrganizationsTab />, { wrapper: Wrapper })
    await user.click(await screen.findByRole("combobox", { name: "Статус" }))
    await user.click(await screen.findByRole("option", { name: "Приостановлена" }))
    expect(await screen.findByRole("alertdialog")).toHaveTextContent("Страница UCOAT останется, курсы на ней будут скрыты")
    await user.click(screen.getByRole("button", { name: "Отмена" }))
    await waitFor(() => expect(screen.queryByRole("alertdialog")).toBeNull())
    expect(update).not.toHaveBeenCalled()

    await user.click(screen.getByRole("combobox", { name: "Статус" }))
    await user.click(await screen.findByRole("option", { name: "Приостановлена" }))
    await user.click(await screen.findByRole("button", { name: "Приостановить" }))
    await waitFor(() => expect(update).toHaveBeenCalledWith("o1", { status: "suspended" }))
  })

  it("saves any other status at once, and calls appointing what it is: adding a director", async () => {
    vi.spyOn(organizationsService, "adminList").mockResolvedValue([org({ status: "approved" })])
    const update = vi.spyOn(organizationsService, "adminUpdate").mockResolvedValue(org())
    const user = userEvent.setup()
    render(<OrganizationsTab />, { wrapper: Wrapper })
    await user.click(await screen.findByRole("combobox", { name: "Статус" }))
    await user.click(await screen.findByRole("option", { name: "Проверена" }))
    await waitFor(() => expect(update).toHaveBeenCalledWith("o1", { status: "verified" }))
    expect(screen.queryByRole("alertdialog")).toBeNull()
    expect(screen.getByLabelText("Добавить директора — почта зарегистрированного аккаунта")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Добавить" })).toBeInTheDocument()
  })
})
