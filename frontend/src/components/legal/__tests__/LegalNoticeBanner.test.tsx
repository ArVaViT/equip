import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import type { ReactNode } from "react"
import { I18nextProvider } from "react-i18next"
import { MemoryRouter } from "react-router-dom"
import i18n from "@/i18n/config"
import { AuthContext } from "@/context/auth-context"
import type { User } from "@/types"
import type { LegalStatus } from "@/services/legal"
import { LegalNoticeBanner } from "../LegalNoticeBanner"

vi.mock("@/services/legal", () => ({
  legalService: {
    status: vi.fn(),
    accept: vi.fn(),
    markNoticeSeen: vi.fn().mockResolvedValue(undefined),
  },
}))

const CORRECTED_PRIVACY = {
  slug: "privacy",
  version: "2.1",
  effective: "2026-10-01",
  required_for: ["admin", "director", "student", "teacher"],
  // The field the whole mechanism turns on: published, announced, not signed.
  requires_consent: false,
}

const user: User = {
  id: "user-1",
  email: "student@example.com",
  full_name: "Test Student",
  avatar_url: null,
  role: "student",
  preferred_locale: "en",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
  onboarding_completed_at: "2026-01-01T00:00:00Z",
}

function Wrapper({ children }: { children: ReactNode }) {
  return (
    <MemoryRouter>
      <I18nextProvider i18n={i18n}>
        <AuthContext.Provider
          value={{
            user,
            loading: false,
            login: vi.fn(),
            register: vi.fn(),
            signInWithGoogle: vi.fn(),
            sendSignInLink: vi.fn(),
            resetPassword: vi.fn(),
            logout: vi.fn(),
            refreshUser: vi.fn(),
            applyUser: vi.fn(),
          }}
        >
          {children}
        </AuthContext.Provider>
      </I18nextProvider>
    </MemoryRouter>
  )
}

const withNotice: LegalStatus = { accepted: [], outstanding: [], notices: [CORRECTED_PRIVACY] }
const quiet: LegalStatus = { accepted: [], outstanding: [], notices: [] }

beforeEach(async () => {
  const { legalService } = await import("@/services/legal")
  vi.mocked(legalService.status).mockResolvedValue(quiet)
  vi.mocked(legalService.markNoticeSeen).mockClear()
})

describe("LegalNoticeBanner", () => {
  it("says nothing when nothing changed", async () => {
    const { legalService } = await import("@/services/legal")
    const { container } = render(
      <Wrapper>
        <LegalNoticeBanner />
      </Wrapper>,
    )
    await waitFor(() => expect(legalService.status).toHaveBeenCalled())
    expect(container.firstChild).toBeNull()
  })

  it("tells the reader what changed without asking for anything", async () => {
    const { legalService } = await import("@/services/legal")
    vi.mocked(legalService.status).mockResolvedValue(withNotice)

    render(
      <Wrapper>
        <LegalNoticeBanner />
      </Wrapper>,
    )

    expect(await screen.findByRole("status")).toBeInTheDocument()
    // No checkbox, no Continue, nothing blocking. A strip, because nothing is
    // being asked.
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument()
    expect(screen.getByRole("link", { name: i18n.t("legalGate.notice.read") })).toHaveAttribute(
      "href",
      "/privacy",
    )
  })

  it("records the dismissal on the server, not in this browser", async () => {
    const { legalService } = await import("@/services/legal")
    vi.mocked(legalService.status).mockResolvedValue(withNotice)

    render(
      <Wrapper>
        <LegalNoticeBanner />
      </Wrapper>,
    )
    await screen.findByRole("status")

    fireEvent.click(screen.getByRole("button", { name: i18n.t("legalGate.notice.dismiss") }))

    // A browser flag would leave the banner waiting on the next device, which
    // teaches people to close banners unread.
    expect(legalService.markNoticeSeen).toHaveBeenCalledWith("privacy", "2.1")
    await waitFor(() => expect(screen.queryByRole("status")).not.toBeInTheDocument())
  })
})
