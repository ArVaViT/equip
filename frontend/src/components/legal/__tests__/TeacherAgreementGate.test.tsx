import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import type { ReactNode } from "react"
import { I18nextProvider } from "react-i18next"
import { MemoryRouter } from "react-router-dom"
import i18n from "@/i18n/config"
import { AuthContext } from "@/context/auth-context"
import { setFirstRunActive } from "@/lib/tourState"
import type { User } from "@/types"
import type { LegalStatus } from "@/services/legal"
import { TeacherAgreementGate } from "../TeacherAgreementGate"
import { getTeacherAgreementOwed } from "../useTeacherAgreement"

vi.mock("@/services/legal", () => ({
  legalService: {
    status: vi.fn(),
    accept: vi.fn().mockResolvedValue({
      slug: "teacher-terms",
      version: "1.0",
      locale: "en",
      accepted_at: "2026-09-17T00:00:00Z",
    }),
    markNoticeSeen: vi.fn().mockResolvedValue(undefined),
  },
}))
vi.mock("@/lib/toast", () => ({ toast: vi.fn() }))

const TEACHER_TERMS = {
  slug: "teacher-terms",
  version: "1.0",
  effective: "2026-09-17",
  required_for: ["admin", "director", "teacher"],
  requires_consent: true,
}

const NOTHING_OWED: LegalStatus = { accepted: [], outstanding: [], notices: [] }
const AGREEMENT_OWED: LegalStatus = { accepted: [], outstanding: [TEACHER_TERMS], notices: [] }

function makeUser(overrides: Partial<User> = {}): User {
  return {
    id: "user-1",
    email: "teacher@example.com",
    full_name: "Test Teacher",
    avatar_url: null,
    role: "student",
    preferred_locale: "en",
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    onboarding_completed_at: "2026-01-01T00:00:00Z",
    ...overrides,
  }
}

const logout = vi.fn()
const refreshUser = vi.fn().mockResolvedValue(undefined)

function Wrapper({
  children,
  user = makeUser(),
  route = "/",
}: {
  children: ReactNode
  user?: User | null
  route?: string
}) {
  return (
    <MemoryRouter initialEntries={[route]}>
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
            logout,
            refreshUser,
            applyUser: vi.fn(),
          }}
        >
          {children}
        </AuthContext.Provider>
      </I18nextProvider>
    </MemoryRouter>
  )
}

const TITLE = () => i18n.t("legalGate.teacher.title")
const CONTINUE = () => i18n.t("legalGate.teacher.next")

beforeEach(async () => {
  const { legalService } = await import("@/services/legal")
  vi.mocked(legalService.status).mockResolvedValue(NOTHING_OWED)
  vi.mocked(legalService.accept).mockClear()
  logout.mockClear()
  refreshUser.mockClear()
  setFirstRunActive(false)
})

afterEach(() => {
  setFirstRunActive(false)
})

describe("TeacherAgreementGate", () => {
  it("does not appear for a student who owes nothing", async () => {
    const { legalService } = await import("@/services/legal")
    const { container } = render(
      <Wrapper>
        <TeacherAgreementGate />
      </Wrapper>,
    )
    await waitFor(() => expect(legalService.status).toHaveBeenCalled())
    expect(container.firstChild).toBeNull()
    expect(screen.queryByText(TITLE())).not.toBeInTheDocument()
  })

  it("appears exactly when the server says the agreement is outstanding", async () => {
    const { legalService } = await import("@/services/legal")
    vi.mocked(legalService.status).mockResolvedValue(AGREEMENT_OWED)

    render(
      <Wrapper>
        <TeacherAgreementGate />
      </Wrapper>,
    )

    // Note the user object still says "student". That is the point: the role
    // is read from the profile row by the server, and an open tab never
    // refetches its own profile — so the promotion arrives through this
    // answer, not through ``user.role``.
    expect(await screen.findByText(TITLE())).toBeInTheDocument()
  })

  it("keeps Continue disabled until the box is ticked, and ticks nothing in advance", async () => {
    const { legalService } = await import("@/services/legal")
    vi.mocked(legalService.status).mockResolvedValue(AGREEMENT_OWED)

    render(
      <Wrapper>
        <TeacherAgreementGate />
      </Wrapper>,
    )
    await screen.findByText(TITLE())

    const checkbox = screen.getByRole("checkbox")
    expect(checkbox).not.toBeChecked()
    expect(screen.getByRole("button", { name: CONTINUE() })).toBeDisabled()

    fireEvent.click(checkbox)
    expect(screen.getByRole("button", { name: CONTINUE() })).toBeEnabled()
  })

  it("records the acceptance with the version and the reader's language, then refetches the role", async () => {
    const { legalService } = await import("@/services/legal")
    vi.mocked(legalService.status).mockResolvedValue(AGREEMENT_OWED)

    render(
      <Wrapper>
        <TeacherAgreementGate />
      </Wrapper>,
    )
    await screen.findByText(TITLE())
    fireEvent.click(screen.getByRole("checkbox"))
    fireEvent.click(screen.getByRole("button", { name: CONTINUE() }))

    await waitFor(() => expect(legalService.accept).toHaveBeenCalledTimes(1))
    expect(legalService.accept).toHaveBeenCalledWith("teacher-terms", "1.0", i18n.language)
    // The role that produced the gate is the one the client has not seen yet.
    await waitFor(() => expect(refreshUser).toHaveBeenCalled())
    await waitFor(() => expect(screen.queryByText(TITLE())).not.toBeInTheDocument())
  })

  it("offers a way out that is not agreeing", async () => {
    const { legalService } = await import("@/services/legal")
    vi.mocked(legalService.status).mockResolvedValue(AGREEMENT_OWED)

    render(
      <Wrapper>
        <TeacherAgreementGate />
      </Wrapper>,
    )
    await screen.findByText(TITLE())

    // A window somebody cannot dismiss must not also hide the door.
    fireEvent.click(screen.getByRole("button", { name: i18n.t("legalGate.signOut") }))
    expect(logout).toHaveBeenCalled()
  })

  it("links to the full text, and does not cover it when the reader follows the link", async () => {
    const { legalService } = await import("@/services/legal")
    vi.mocked(legalService.status).mockResolvedValue(AGREEMENT_OWED)

    const { container } = render(
      <Wrapper route="/teacher-terms">
        <TeacherAgreementGate />
      </Wrapper>,
    )
    await waitFor(() => expect(legalService.status).toHaveBeenCalled())

    // The first-run gate shipped this bug to production: the overlay mounts on
    // every route, so the tab it opens is a tab it covers.
    expect(container.firstChild).toBeNull()
  })

  it("waits for the consent gate rather than stacking on top of it", async () => {
    const { legalService } = await import("@/services/legal")
    vi.mocked(legalService.status).mockResolvedValue(AGREEMENT_OWED)
    setFirstRunActive(true)

    const { container } = render(
      <Wrapper>
        <TeacherAgreementGate />
      </Wrapper>,
    )
    await waitFor(() => expect(legalService.status).toHaveBeenCalled())

    // Being congratulated before being asked to consent is the wrong order.
    expect(container.firstChild).toBeNull()
  })

  it("publishes what the route guard reads, so /teacher/* is refused and then is not", async () => {
    const { legalService } = await import("@/services/legal")
    vi.mocked(legalService.status).mockResolvedValue(AGREEMENT_OWED)

    render(
      <Wrapper>
        <TeacherAgreementGate />
      </Wrapper>,
    )
    await screen.findByText(TITLE())
    expect(getTeacherAgreementOwed()).toBe(true)

    fireEvent.click(screen.getByRole("checkbox"))
    fireEvent.click(screen.getByRole("button", { name: CONTINUE() }))

    await waitFor(() => expect(getTeacherAgreementOwed()).toBe(false))
  })
})
