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
import { getTeacherAgreementOwed, subscribeTeacherAgreement } from "../useTeacherAgreement"

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
const viewAs = vi.hoisted(() => ({ active: null as null | { userId: string } }))
vi.mock("@/lib/viewAs", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/viewAs")>()),
  activeViewAs: () => viewAs.active,
}))

const TEACHER_TERMS = {
  slug: "teacher-terms",
  version: "1.0",
  effective: "2026-09-17",
  required_for: ["admin", "director", "teacher"],
  requires_consent: true,
}

const SCHOOL_AGREEMENT = {
  slug: "school-agreement",
  version: "1.0",
  effective: "2026-09-17",
  required_for: ["director"],
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
  viewAs.active = null
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

  it("accepts nothing until the box is ticked, and ticks nothing in advance", async () => {
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
    fireEvent.click(screen.getByRole("button", { name: CONTINUE() }))
    expect(legalService.accept).not.toHaveBeenCalled()
  })

  it("points at the box when the button is pressed without it, instead of doing nothing", async () => {
    // A new teacher on a phone tapped around the box six times before hitting
    // it (RUM, 2026-09-19). A disabled button answered none of those taps.
    const { legalService } = await import("@/services/legal")
    vi.mocked(legalService.status).mockResolvedValue(AGREEMENT_OWED)

    render(
      <Wrapper>
        <TeacherAgreementGate />
      </Wrapper>,
    )
    await screen.findByText(TITLE())

    const button = screen.getByRole("button", { name: CONTINUE() })
    expect(button).toBeEnabled()
    fireEvent.click(button)

    const checkbox = screen.getByRole("checkbox")
    expect(screen.getByRole("alert")).toHaveTextContent(i18n.t("legalGate.teacher.tickFirst"))
    expect(checkbox).toHaveAttribute("aria-invalid", "true")
    expect(checkbox).toHaveFocus()

    fireEvent.click(checkbox)
    expect(screen.queryByRole("alert")).not.toBeInTheDocument()
    expect(checkbox).not.toHaveAttribute("aria-invalid")
  })

  it("ticks the box from anywhere on its row, not only the 16px square", async () => {
    const { legalService } = await import("@/services/legal")
    vi.mocked(legalService.status).mockResolvedValue(AGREEMENT_OWED)

    render(
      <Wrapper>
        <TeacherAgreementGate />
      </Wrapper>,
    )
    await screen.findByText(TITLE())

    const checkbox = screen.getByRole("checkbox")
    const row = checkbox.closest("label")
    expect(row, "the box and its words are one label").not.toBeNull()
    expect(row!.className).toContain("min-h-11")
    fireEvent.click(row!)
    expect(checkbox).toBeChecked()
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

  // The one director on the platform owed the School Agreement and nothing in
  // the app asked for it: the server refused his every change (seventeen 403s
  // grading one paper, 2026-11-22) while no screen offered a way to accept.
  it("asks a director for the School Agreement, in its own words, and records exactly that", async () => {
    const { legalService } = await import("@/services/legal")
    vi.mocked(legalService.status).mockResolvedValue({ accepted: [], outstanding: [SCHOOL_AGREEMENT], notices: [] })

    render(
      <Wrapper user={makeUser({ role: "director" })}>
        <TeacherAgreementGate />
      </Wrapper>,
    )
    expect(await screen.findByText(i18n.t("legalGate.school.title"))).toBeInTheDocument()
    expect(screen.queryByText(TITLE())).not.toBeInTheDocument()
    expect(screen.getByRole("link", { name: i18n.t("legal.schoolAgreement") })).toHaveAttribute("href", "/school-agreement")

    fireEvent.click(screen.getByRole("checkbox"))
    fireEvent.click(screen.getByRole("button", { name: i18n.t("legalGate.school.next") }))
    await waitFor(() => expect(legalService.accept).toHaveBeenCalledWith("school-agreement", "1.0", i18n.language))
  })

  it("asks for the second document at once, with an empty box, and records both", async () => {
    const { legalService } = await import("@/services/legal")
    vi.mocked(legalService.status)
      .mockResolvedValueOnce({ accepted: [], outstanding: [TEACHER_TERMS, SCHOOL_AGREEMENT], notices: [] })
      .mockResolvedValue({ accepted: [], outstanding: [SCHOOL_AGREEMENT], notices: [] })

    render(
      <Wrapper user={makeUser({ role: "director" })}>
        <TeacherAgreementGate />
      </Wrapper>,
    )
    await screen.findByText(TITLE())
    const published: boolean[] = []
    const unsubscribe = subscribeTeacherAgreement(() => published.push(getTeacherAgreementOwed()))
    fireEvent.click(screen.getByRole("checkbox"))
    fireEvent.click(screen.getByRole("button", { name: CONTINUE() }))
    await waitFor(() => expect(legalService.accept).toHaveBeenCalledWith("teacher-terms", "1.0", i18n.language))

    // The school's acceptance must not ride on the tick given for the teacher terms.
    expect(await screen.findByText(i18n.t("legalGate.school.title"))).toBeInTheDocument()
    expect(screen.getByRole("checkbox")).not.toBeChecked()
    expect(legalService.accept).toHaveBeenCalledTimes(1)
    // And at no point in between did the route guard think nothing was owed:
    // every value published since the first acceptance was "still owed".
    expect(getTeacherAgreementOwed()).toBe(true)
    expect(published.every(Boolean)).toBe(true)
    unsubscribe()

    fireEvent.click(screen.getByRole("checkbox"))
    fireEvent.click(screen.getByRole("button", { name: i18n.t("legalGate.school.next") }))
    await waitFor(() => expect(legalService.accept).toHaveBeenCalledWith("school-agreement", "1.0", i18n.language))
    expect(legalService.accept).toHaveBeenCalledTimes(2)
  })

  it("does not bring back a document accepted a moment ago when a stale answer still lists it", async () => {
    const { legalService } = await import("@/services/legal")
    const stale = { accepted: [], outstanding: [TEACHER_TERMS, SCHOOL_AGREEMENT], notices: [] }
    vi.mocked(legalService.status).mockResolvedValue(stale)

    render(
      <Wrapper user={makeUser({ role: "director" })}>
        <TeacherAgreementGate />
      </Wrapper>,
    )
    await screen.findByText(TITLE())
    fireEvent.click(screen.getByRole("checkbox"))
    fireEvent.click(screen.getByRole("button", { name: CONTINUE() }))
    await waitFor(() => expect(legalService.accept).toHaveBeenCalledTimes(1))
    // The check after accepting answers with the old list, teacher terms included.
    await waitFor(() => expect(vi.mocked(legalService.status).mock.calls.length).toBeGreaterThanOrEqual(2))

    expect(await screen.findByText(i18n.t("legalGate.school.title"))).toBeInTheDocument()
    expect(screen.queryByText(TITLE())).not.toBeInTheDocument()
    expect(getTeacherAgreementOwed()).toBe(true)
  })

  it("names the School Agreement in its checkbox, in every language", async () => {
    const bundles = { en: (await import("@/i18n/locales/en.json")).default, ru: (await import("@/i18n/locales/ru.json")).default, de: (await import("@/i18n/locales/de.json")).default, uk: (await import("@/i18n/locales/uk.json")).default }
    // By word stems: Russian and Ukrainian put the name in the accusative
    // («Угоду зі школою»), which is still the same document named.
    for (const [locale, bundle] of Object.entries(bundles)) {
      const box = bundle.legalGate.school.checkbox.toLowerCase()
      for (const word of bundle.legal.schoolAgreement.toLowerCase().split(/\s+/)) {
        expect(box, `${locale}: the checkbox does not name the School Agreement`).toContain(word.slice(0, Math.max(2, word.length - 1)))
      }
    }
  })

  it("does not cover the School Agreement when the director opens it to read", async () => {
    const { legalService } = await import("@/services/legal")
    vi.mocked(legalService.status).mockResolvedValue({ accepted: [], outstanding: [SCHOOL_AGREEMENT], notices: [] })

    const { container } = render(
      <Wrapper route="/school-agreement" user={makeUser({ role: "director" })}>
        <TeacherAgreementGate />
      </Wrapper>,
    )
    await waitFor(() => expect(legalService.status).toHaveBeenCalled())
    expect(container.firstChild).toBeNull()
  })

  it("does not raise the gate for nobody when an answer lands after sign-out", async () => {
    const { legalService } = await import("@/services/legal")
    let answer: (status: LegalStatus) => void = () => {}
    vi.mocked(legalService.status).mockReturnValue(new Promise<LegalStatus>((resolve) => (answer = resolve)))

    const { container, rerender } = render(
      <Wrapper user={makeUser({ role: "director" })}>
        <TeacherAgreementGate />
      </Wrapper>,
    )
    await waitFor(() => expect(legalService.status).toHaveBeenCalled())
    rerender(
      <Wrapper user={null}>
        <TeacherAgreementGate />
      </Wrapper>,
    )
    answer({ accepted: [], outstanding: [SCHOOL_AGREEMENT], notices: [] })
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(container.firstChild).toBeNull()
    expect(getTeacherAgreementOwed()).toBe(false)
  })

  it("lets a director read the providers the School Agreement asks the school to accept", async () => {
    const { legalService } = await import("@/services/legal")
    vi.mocked(legalService.status).mockResolvedValue({ accepted: [], outstanding: [SCHOOL_AGREEMENT], notices: [] })

    const { container } = render(
      <Wrapper route="/privacy/providers" user={makeUser({ role: "director" })}>
        <TeacherAgreementGate />
      </Wrapper>,
    )
    await waitFor(() => expect(legalService.status).toHaveBeenCalled())
    expect(container.firstChild).toBeNull()
  })

  it("stays out of the way while an admin views as somebody who owes it", async () => {
    // The view is read-only: accepting would be refused, and the gate would
    // cover the banner whose button ends the view.
    const { legalService } = await import("@/services/legal")
    vi.mocked(legalService.status).mockResolvedValue({ accepted: [], outstanding: [SCHOOL_AGREEMENT], notices: [] })
    viewAs.active = { userId: "director-1" }

    const { container } = render(
      <Wrapper user={makeUser({ role: "director" })}>
        <TeacherAgreementGate />
      </Wrapper>,
    )
    await waitFor(() => expect(legalService.status).toHaveBeenCalled())
    expect(container.firstChild).toBeNull()
  })

  it("says so inside the gate when the acceptance could not be saved", async () => {
    // A toast renders beneath this overlay: a failed save looked like a
    // spinner that stopped and nothing else.
    const { legalService } = await import("@/services/legal")
    vi.mocked(legalService.status).mockResolvedValue({ accepted: [], outstanding: [SCHOOL_AGREEMENT], notices: [] })
    vi.mocked(legalService.accept).mockRejectedValueOnce(new Error("Network Error"))

    render(
      <Wrapper user={makeUser({ role: "director" })}>
        <TeacherAgreementGate />
      </Wrapper>,
    )
    await screen.findByText(i18n.t("legalGate.school.title"))
    fireEvent.click(screen.getByRole("checkbox"))
    fireEvent.click(screen.getByRole("button", { name: i18n.t("legalGate.school.next") }))

    expect(await screen.findByRole("alert")).toHaveTextContent(i18n.t("legalGate.school.saveFailed"))
    expect(screen.getByText(i18n.t("legalGate.school.title"))).toBeInTheDocument()
  })

  it("does not turn an admin viewing as somebody away from /teacher/*", async () => {
    const { legalService } = await import("@/services/legal")
    vi.mocked(legalService.status).mockResolvedValue({ accepted: [], outstanding: [SCHOOL_AGREEMENT], notices: [] })
    viewAs.active = { userId: "director-1" }

    render(
      <Wrapper user={makeUser({ role: "director" })}>
        <TeacherAgreementGate />
      </Wrapper>,
    )
    await waitFor(() => expect(legalService.status).toHaveBeenCalled())
    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(getTeacherAgreementOwed()).toBe(false)
  })
})
