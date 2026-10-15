/**
 * Where each invitation leads, and a header that fits a phone.
 *
 * A list of many rows has to say what each one grants by name: the
 * organization, the course, or an account and nothing else. And on a
 * 390px screen the title and the «create» button, side by side, pushed the
 * card past the viewport (2026-10-03).
 */
import type { ReactNode } from "react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { render, screen, waitFor } from "@testing-library/react"
import { I18nextProvider } from "react-i18next"

import i18n from "@/i18n/config"
import { ConfirmProvider } from "@/components/ui/alert-dialog"
import { InvitationsTab } from "@/pages/Admin/invitations/InvitationsTab"

const listInvitations = vi.fn()

vi.mock("@/services/invitations", () => ({
  invitationsService: {
    listInvitations: (...args: unknown[]) => listInvitations(...args),
    revokeInvitation: vi.fn(),
    createInvitation: vi.fn(),
  },
}))

const BASE = {
  role: "student",
  status: "pending",
  is_expired: false,
  created_at: "2026-09-12T00:00:00Z",
  expires_at: "2026-09-19T00:00:00Z",
  invited_by: "admin-1",
  accepted_at: null,
  fulfilled_at: null,
  organization_name: "UCOAT",
}

function Wrapper({ children }: { children: ReactNode }) {
  return (
    <I18nextProvider i18n={i18n}>
      <ConfirmProvider>{children}</ConfirmProvider>
    </I18nextProvider>
  )
}

describe("InvitationsTab — where each invitation leads", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru")
    listInvitations.mockReset().mockResolvedValue([
      { ...BASE, id: "a", email: "account@example.com", scope: "platform" },
      { ...BASE, id: "o", email: "member@example.com", scope: "organization" },
      { ...BASE, id: "c", email: "seat@example.com", scope: "course", course_id: "acts", course_title: "Книга Деяний" },
      { ...BASE, id: "old", email: "old.server@example.com", scope: "course", course_id: "x", course_title: null },
    ])
  })
  afterEach(async () => {
    await i18n.changeLanguage("en")
  })

  it("names the organization, the course, or «account only» — once per row in each layout", async () => {
    render(<InvitationsTab />, { wrapper: Wrapper })
    await waitFor(() => expect(screen.getAllByText("seat@example.com").length).toBeGreaterThan(0))
    // Two layouts (the phone cards and the table) each render every row once.
    expect(screen.getAllByText("Только аккаунт")).toHaveLength(2)
    expect(screen.getAllByText("UCOAT")).toHaveLength(2)
    expect(screen.getAllByText("Книга Деяний")).toHaveLength(2)
    // A server that sends no title: the course invitation still says it is one.
    expect(screen.getAllByText("На курс")).toHaveLength(2)
    expect(screen.getByRole("columnheader", { name: "Куда" })).toBeInTheDocument()
  })

  it("stacks the title over the button below the first breakpoint", async () => {
    render(<InvitationsTab />, { wrapper: Wrapper })
    const title = await screen.findByText("Приглашения", { selector: "h3, div" })
    // jsdom lays nothing out; the arrangement is the classes, so they are
    // what is checked: a column by default, a row only from `sm` up.
    expect(title.parentElement?.className).toMatch(/\bflex-col\b/)
    expect(title.parentElement?.className).toMatch(/\bsm:flex-row\b/)
  })
})
