import { act, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { useState, type ReactNode } from "react"
import { I18nextProvider } from "react-i18next"
import { MotionConfig } from "motion/react"
import { MemoryRouter } from "react-router-dom"
import i18n from "@/i18n/config"
import { axe } from "@/test/a11y"
import { AuthContext } from "@/context/auth-context"
import { ThemeContext } from "@/context/theme-context"
import { FirstRunFlow } from "../FirstRunFlow"
import { decideInitialStep } from "../firstRunStep"
import { getFirstRunActive, setFirstRunActive } from "@/lib/tourState"
import type { User } from "@/types"
import type { LegalStatus } from "@/services/legal"

// Mock the services so the steps don't try to hit a real backend. Each
// test asserts the orchestration, not the network.
vi.mock("@/services/users", () => ({
  usersService: {
    updateProfile: vi.fn().mockResolvedValue({}),
  },
}))
vi.mock("@/services/onboarding", () => ({
  onboardingService: {
    complete: vi.fn().mockResolvedValue({
      id: "user-1",
      email: "test@example.com",
      full_name: "Test User",
      avatar_url: null,
      role: "student",
      preferred_locale: "en",
      locale_source: "chosen",
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
      onboarding_completed_at: "2026-09-07T00:00:00Z",
    }),
  },
}))
// One public course by default so the picker has something to show. Tests
// that want the empty-catalogue auto-skip override this per test.
vi.mock("@/services/courses", () => ({
  coursesService: {
    getCourses: vi.fn().mockResolvedValue([
      {
        id: "course-1",
        title: "Acts",
        description: null,
        image_url: null,
        access_mode: "public",
        status: "published",
        modules: [],
      },
    ]),
  },
}))
vi.mock("@/services/enrollments", () => ({
  enrollmentsService: {
    enrollInCourse: vi.fn().mockResolvedValue({}),
  },
}))
vi.mock("@/lib/toast", () => ({
  toast: vi.fn(),
}))
// The legal gate is server-driven: the flow asks what is still outstanding
// rather than reading a localStorage flag. Default here is "everything
// outstanding", which is what a brand-new user sees.
vi.mock("@/services/legal", () => ({
  legalService: {
    documents: vi.fn().mockResolvedValue([
      { slug: "privacy", version: "1.0" },
      { slug: "terms", version: "1.0" },
    ]),
    status: vi.fn().mockResolvedValue({
      accepted: [],
      outstanding: [
        { slug: "privacy", version: "1.0" },
        { slug: "terms", version: "1.0" },
      ],
    }),
    accept: vi.fn().mockResolvedValue({
      slug: "privacy",
      version: "1.0",
      locale: "en",
      accepted_at: "2026-08-13T00:00:00Z",
    }),
  },
}))
vi.mock("@/lib/images", () => ({
  toProxyImage: (url: string) => url,
}))

const NOTHING_OWED: LegalStatus = {
  accepted: [
    { slug: "privacy", version: "1.0", locale: "en", accepted_at: "2026-08-13T00:00:00Z" },
    { slug: "terms", version: "1.0", locale: "en", accepted_at: "2026-08-13T00:00:00Z" },
  ],
  outstanding: [],
}

function makeUser(overrides: Partial<User> = {}): User {
  return {
    id: "user-1",
    email: "test@example.com",
    full_name: "Test User",
    avatar_url: null,
    role: "student",
    preferred_locale: "en",
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    onboarding_completed_at: null,
    ...overrides,
  }
}

const applyUser = vi.fn()

function Wrapper({
  children,
  user = makeUser(),
  route = "/",
  apply = applyUser,
}: {
  children: ReactNode
  user?: User | null
  route?: string
  apply?: (next: User) => void
}) {
  return (
    <MemoryRouter initialEntries={[route]}>
      <I18nextProvider i18n={i18n}>
        {/* MotionConfig with reducedMotion="always" makes
            ``AnimatePresence`` enter/exit animations resolve
            synchronously in tests, so post-click queries land on the
            new step without ``findBy``-polling. */}
        <MotionConfig reducedMotion="always">
          <ThemeContext.Provider value={{ theme: "light", toggleTheme: vi.fn() }}>
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
                refreshUser: vi.fn().mockResolvedValue(undefined),
                applyUser: apply,
              }}
            >
              {children}
            </AuthContext.Provider>
          </ThemeContext.Provider>
        </MotionConfig>
      </I18nextProvider>
    </MemoryRouter>
  )
}

/**
 * The real ``AuthProvider`` replaces the profile when ``applyUser`` is
 * called, and the flow re-derives its step from the new one. The tests that
 * are about that re-derivation need a wrapper that does the same.
 */
function StatefulWrapper({ children, initial }: { children: ReactNode; initial: User }) {
  const [user, setUser] = useState<User>(initial)
  return (
    <Wrapper
      user={user}
      apply={(next) => {
        applyUser(next)
        setUser(next)
      }}
    >
      {children}
    </Wrapper>
  )
}

const PRIVACY_TITLE = () => i18n.t("firstRun.privacy.title")
const RENEWAL_TITLE = () => i18n.t("firstRun.privacy.renewal.title")
const NAME_TITLE = () => i18n.t("firstRun.name.title")
// The picker heading is personalised when the profile has a first name
// ("Test, pick a course to begin with" vs "Pick a course to begin with");
// the regex covers both shapes.
const PICKER_TITLE = /pick a course to begin with/i

beforeEach(() => {
  window.localStorage.clear()
  setFirstRunActive(false)
})

afterEach(() => {
  setFirstRunActive(false)
  vi.clearAllMocks()
})

describe("decideInitialStep", () => {
  const student = makeUser()

  it("shows nothing to nobody", () => {
    expect(decideInitialStep(null, null)).toBe("done")
  })

  it("asks for consent first, and trusts the cache only until the server answers", () => {
    expect(decideInitialStep(student, null)).toBe("privacy")
    window.localStorage.setItem("equip.privacy.accepted.user-1", "1")
    expect(decideInitialStep(student, null)).toBe("picker")
    // The server outranks the cache in both directions.
    expect(decideInitialStep(student, true)).toBe("privacy")
    expect(decideInitialStep(student, false)).toBe("picker")
  })

  it("shows nothing to somebody the profile says has finished", () => {
    expect(decideInitialStep(makeUser({ onboarding_completed_at: "2026-09-01T00:00:00Z" }), false)).toBe("done")
  })

  it("lets a browser that finished before the server kept a record pass", () => {
    window.localStorage.setItem("equip.first-run.completed.user-1", "1")
    expect(decideInitialStep(student, false)).toBe("done")
  })

  it("asks a nameless student for a name, once", () => {
    const nameless = makeUser({ full_name: "" })
    expect(decideInitialStep(nameless, false)).toBe("name")
    expect(decideInitialStep(makeUser({ full_name: "   " }), false)).toBe("name")
    expect(decideInitialStep(nameless, false, true)).toBe("picker")
  })

  it("never shows the picker to a teacher, a director or an admin", () => {
    for (const role of ["teacher", "director", "admin"] as const) {
      expect(decideInitialStep(makeUser({ role, full_name: "" }), false)).toBe("done")
    }
  })
})

describe("FirstRunFlow", () => {
  it("renders nothing when there is no signed-in user", () => {
    const { container } = render(
      <Wrapper user={null}>
        <FirstRunFlow />
      </Wrapper>,
    )
    expect(container.firstChild).toBeNull()
    expect(getFirstRunActive()).toBe(false)
  })

  it("starts on Privacy when nothing is known", () => {
    render(
      <Wrapper>
        <FirstRunFlow />
      </Wrapper>,
    )
    expect(screen.getByText(PRIVACY_TITLE())).toBeInTheDocument()
    expect(getFirstRunActive()).toBe(true)
  })

  it("Continue button is disabled until the checkbox is checked", () => {
    render(
      <Wrapper>
        <FirstRunFlow />
      </Wrapper>,
    )
    const next = screen.getByRole("button", { name: i18n.t("firstRun.privacy.next") })
    expect(next).toBeDisabled()
    fireEvent.click(screen.getByRole("checkbox"))
    expect(next).not.toBeDisabled()
  })

  it("records the acceptance on the server, then goes straight to the picker for a named student", async () => {
    const { legalService } = await import("@/services/legal")
    render(
      <Wrapper>
        <FirstRunFlow />
      </Wrapper>,
    )
    fireEvent.click(screen.getByRole("checkbox"))
    fireEvent.click(screen.getByRole("button", { name: i18n.t("firstRun.privacy.next") }))

    // Both documents, because that is what the checkbox sentence names.
    await waitFor(() => expect(legalService.accept).toHaveBeenCalledTimes(2))
    expect(vi.mocked(legalService.accept).mock.calls.map((c) => c[0])).toEqual(["privacy", "terms"])
    // The flag is still written, but it is a cache now — it stops the gate
    // flashing before the server answers, and proves nothing on its own.
    await waitFor(() => expect(window.localStorage.getItem("equip.privacy.accepted.user-1")).toBe("1"))
    // No "quick setup" in between: the profile already has a name, and the
    // photo, theme and language have homes elsewhere.
    expect(await screen.findByText(PICKER_TITLE)).toBeInTheDocument()
    expect(screen.queryByText(NAME_TITLE())).not.toBeInTheDocument()
  })

  it("asks a nameless student for a name before the picker, and Skip moves on", async () => {
    const { legalService } = await import("@/services/legal")
    vi.mocked(legalService.status).mockResolvedValueOnce(NOTHING_OWED)
    window.localStorage.setItem("equip.privacy.accepted.user-1", "1")
    render(
      <Wrapper user={makeUser({ full_name: "" })}>
        <FirstRunFlow />
      </Wrapper>,
    )
    expect(screen.getByText(NAME_TITLE())).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: i18n.t("firstRun.name.skip") }))
    expect(await screen.findByText(PICKER_TITLE)).toBeInTheDocument()
  })

  it("does not send somebody back to the name step when the legal answer lands after they skipped it", async () => {
    const { legalService } = await import("@/services/legal")
    let answer!: (status: LegalStatus) => void
    vi.mocked(legalService.status).mockImplementationOnce(
      () =>
        new Promise<LegalStatus>((resolve) => {
          answer = resolve
        }),
    )
    window.localStorage.setItem("equip.privacy.accepted.user-1", "1")
    render(
      <Wrapper user={makeUser({ full_name: "" })}>
        <FirstRunFlow />
      </Wrapper>,
    )
    fireEvent.click(screen.getByRole("button", { name: i18n.t("firstRun.name.skip") }))
    expect(await screen.findByText(PICKER_TITLE)).toBeInTheDocument()

    await act(async () => {
      answer(NOTHING_OWED)
    })

    // ``AnimatePresence`` keeps the outgoing step in the DOM for a beat, so
    // the visible heading cannot tell a stay from a departure this early.
    // The dialog's accessible name follows the step synchronously.
    expect(screen.getByRole("dialog")).toHaveAccessibleName(i18n.t("firstRun.picker.eyebrow"))
    expect(screen.getByText(PICKER_TITLE)).toBeInTheDocument()
  })

  it("saves the name and moves on", async () => {
    const { usersService } = await import("@/services/users")
    const { legalService } = await import("@/services/legal")
    vi.mocked(legalService.status).mockResolvedValueOnce(NOTHING_OWED)
    window.localStorage.setItem("equip.privacy.accepted.user-1", "1")
    render(
      <Wrapper user={makeUser({ full_name: null })}>
        <FirstRunFlow />
      </Wrapper>,
    )
    const submit = screen.getByRole("button", { name: i18n.t("firstRun.name.submit") })
    expect(submit).toBeDisabled()
    fireEvent.change(screen.getByLabelText(i18n.t("firstRun.name.label")), { target: { value: "  Anna Koval " } })
    fireEvent.click(submit)

    await waitFor(() => expect(usersService.updateProfile).toHaveBeenCalledWith({ full_name: "Anna Koval" }))
    expect(await screen.findByText(PICKER_TITLE)).toBeInTheDocument()
  })

  it("shows nothing to somebody whose profile says the flow is finished — in a browser that never saw it", async () => {
    const { legalService } = await import("@/services/legal")
    vi.mocked(legalService.status).mockResolvedValueOnce(NOTHING_OWED)
    const { container } = render(
      <Wrapper user={makeUser({ onboarding_completed_at: "2026-09-01T00:00:00Z" })}>
        <FirstRunFlow />
      </Wrapper>,
    )
    // Consent is the one thing the cache may not vouch for, so the gate is
    // up until the server answers; the rest of the flow is not.
    await waitFor(() => expect(container.firstChild).toBeNull())
    expect(getFirstRunActive()).toBe(false)
  })

  it("tells the server when this browser finished the flow before the server kept a record", async () => {
    const { legalService } = await import("@/services/legal")
    const { onboardingService } = await import("@/services/onboarding")
    vi.mocked(legalService.status).mockResolvedValueOnce(NOTHING_OWED)
    window.localStorage.setItem("equip.privacy.accepted.user-1", "1")
    window.localStorage.setItem("equip.first-run.completed.user-1", "1")
    const { container } = render(
      <Wrapper>
        <FirstRunFlow />
      </Wrapper>,
    )
    expect(container.firstChild).toBeNull()
    await waitFor(() => expect(onboardingService.complete).toHaveBeenCalledTimes(1))
    // And the answer is applied, so nothing waits for the next reload.
    await waitFor(() => expect(applyUser).toHaveBeenCalledTimes(1))
    expect(applyUser.mock.calls[0]?.[0]).toMatchObject({ onboarding_completed_at: "2026-09-07T00:00:00Z" })
  })

  it("does not report a completion the server already holds", async () => {
    const { legalService } = await import("@/services/legal")
    const { onboardingService } = await import("@/services/onboarding")
    vi.mocked(legalService.status).mockResolvedValueOnce(NOTHING_OWED)
    window.localStorage.setItem("equip.first-run.completed.user-1", "1")
    render(
      <Wrapper user={makeUser({ onboarding_completed_at: "2026-09-01T00:00:00Z" })}>
        <FirstRunFlow />
      </Wrapper>,
    )
    await waitFor(() => expect(legalService.status).toHaveBeenCalled())
    await act(async () => {})
    expect(onboardingService.complete).not.toHaveBeenCalled()
  })

  it("closing the picker marks the flow finished on the server and in the cache", async () => {
    const { onboardingService } = await import("@/services/onboarding")
    const { legalService } = await import("@/services/legal")
    vi.mocked(legalService.status).mockResolvedValueOnce(NOTHING_OWED)
    window.localStorage.setItem("equip.privacy.accepted.user-1", "1")
    const { container } = render(
      <Wrapper>
        <FirstRunFlow />
      </Wrapper>,
    )
    fireEvent.click(await screen.findByRole("button", { name: i18n.t("firstRun.picker.skip") }))

    expect(window.localStorage.getItem("equip.first-run.completed.user-1")).toBe("1")
    expect(window.localStorage.getItem("equip.grand-tour.seen.user-1")).toBe("1")
    await waitFor(() => expect(onboardingService.complete).toHaveBeenCalledTimes(1))
    await waitFor(() => expect(container.firstChild).toBeNull())
    expect(getFirstRunActive()).toBe(false)
  })

  it("never shows a teacher the picker, and records that their flow is done", async () => {
    const { legalService } = await import("@/services/legal")
    const { onboardingService } = await import("@/services/onboarding")
    vi.mocked(legalService.status).mockResolvedValueOnce(NOTHING_OWED)
    window.localStorage.setItem("equip.privacy.accepted.user-1", "1")
    const { container } = render(
      <Wrapper user={makeUser({ role: "teacher", full_name: "" })}>
        <FirstRunFlow />
      </Wrapper>,
    )
    expect(container.firstChild).toBeNull()
    await waitFor(() => expect(onboardingService.complete).toHaveBeenCalledTimes(1))
  })

  it("tells somebody who accepted an earlier version that the documents changed, not «Before we begin»", async () => {
    const { legalService } = await import("@/services/legal")
    vi.mocked(legalService.status).mockResolvedValueOnce({
      accepted: [
        { slug: "privacy", version: "0.9", locale: "en", accepted_at: "2026-05-01T00:00:00Z" },
        { slug: "terms", version: "0.9", locale: "en", accepted_at: "2026-05-01T00:00:00Z" },
      ],
      outstanding: [
        { slug: "privacy", version: "1.0" },
        { slug: "terms", version: "1.0" },
      ],
    })
    render(
      <Wrapper user={makeUser({ onboarding_completed_at: "2026-05-01T00:00:00Z" })}>
        <FirstRunFlow />
      </Wrapper>,
    )
    expect(await screen.findByText(RENEWAL_TITLE())).toBeInTheDocument()
    expect(screen.queryByText(PRIVACY_TITLE())).not.toBeInTheDocument()
  })

  it("sends somebody re-accepting changed documents straight back into the product", async () => {
    const { legalService } = await import("@/services/legal")
    vi.mocked(legalService.status).mockResolvedValueOnce({
      accepted: [{ slug: "privacy", version: "0.9", locale: "en", accepted_at: "2026-05-01T00:00:00Z" }],
      outstanding: [{ slug: "privacy", version: "1.0" }],
    })
    const { container } = render(
      <Wrapper user={makeUser({ onboarding_completed_at: "2026-05-01T00:00:00Z" })}>
        <FirstRunFlow />
      </Wrapper>,
    )
    await screen.findByText(RENEWAL_TITLE())
    fireEvent.click(screen.getByRole("checkbox"))
    fireEvent.click(screen.getByRole("button", { name: i18n.t("firstRun.privacy.next") }))

    await waitFor(() => expect(container.firstChild).toBeNull())
    expect(screen.queryByText(PICKER_TITLE)).not.toBeInTheDocument()
  })

  it("scopes flags by user id (no cross-account leak)", () => {
    window.localStorage.setItem("equip.privacy.accepted.user-A", "1")
    window.localStorage.setItem("equip.first-run.completed.user-A", "1")
    render(
      <Wrapper user={makeUser({ id: "user-B" })}>
        <FirstRunFlow />
      </Wrapper>,
    )
    // user-B should see the Privacy screen even though user-A finished
    expect(screen.getByText(PRIVACY_TITLE())).toBeInTheDocument()
  })

  it("keeps the splash on screen while the completion report lands", async () => {
    const { onboardingService } = await import("@/services/onboarding")
    const { legalService } = await import("@/services/legal")
    vi.mocked(legalService.status).mockResolvedValueOnce(NOTHING_OWED)
    window.localStorage.setItem("equip.privacy.accepted.user-1", "1")
    render(
      <StatefulWrapper initial={makeUser()}>
        <FirstRunFlow />
      </StatefulWrapper>,
    )
    // The card's accessible name is the title plus the module count.
    fireEvent.click(await screen.findByRole("button", { name: /Acts/ }))
    fireEvent.click(screen.getByRole("button", { name: i18n.t("firstRun.picker.enrollOne") }))

    // The celebration: the course title, big, on its own screen.
    expect(await screen.findByRole("status")).toBeInTheDocument()
    await waitFor(() => expect(onboardingService.complete).toHaveBeenCalledTimes(1))
    // The server's answer is applied and the profile now says "finished" —
    // which must not cut the celebration short or lose the navigation.
    await waitFor(() =>
      expect(applyUser).toHaveBeenCalledWith(expect.objectContaining({ onboarding_completed_at: expect.any(String) })),
    )
    await act(async () => {})
    expect(screen.getByRole("status")).toBeInTheDocument()
  })

  it("unmount cleanup resets the firstRunActive signal", () => {
    const { unmount } = render(
      <Wrapper>
        <FirstRunFlow />
      </Wrapper>,
    )
    expect(getFirstRunActive()).toBe(true)
    act(() => {
      unmount()
    })
    expect(getFirstRunActive()).toBe(false)
  })

  it("renders the initial Privacy step without a11y violations", async () => {
    const { container } = render(
      <Wrapper>
        <FirstRunFlow />
      </Wrapper>,
    )
    expect(screen.getByText(PRIVACY_TITLE())).toBeInTheDocument()
    expect(await axe(container)).toHaveNoViolations()
  })

  it("renders the name step without a11y violations", async () => {
    window.localStorage.setItem("equip.privacy.accepted.user-1", "1")
    const { container } = render(
      <Wrapper user={makeUser({ full_name: "" })}>
        <FirstRunFlow />
      </Wrapper>,
    )
    expect(screen.getByText(NAME_TITLE())).toBeInTheDocument()
    expect(await axe(container)).toHaveNoViolations()
  })

  it("does not cover the documents it asks people to read", async () => {
    // Found on production minutes after shipping: this component mounts on
    // every route, so opening «Политика конфиденциальности» from the gate
    // showed the gate again, on top of the document.
    for (const route of ["/privacy", "/terms"]) {
      const { unmount } = render(
        <Wrapper route={route}>
          <FirstRunFlow />
        </Wrapper>,
      )
      expect(screen.queryByText(PRIVACY_TITLE())).not.toBeInTheDocument()
      // And the tour signal must stay off, or every per-page tour on those
      // routes silently refuses to start.
      expect(getFirstRunActive()).toBe(false)
      unmount()
    }
  })

  it("still gates every other route", () => {
    render(
      <Wrapper route="/courses">
        <FirstRunFlow />
      </Wrapper>,
    )
    expect(screen.getByText(PRIVACY_TITLE())).toBeInTheDocument()
  })
})
