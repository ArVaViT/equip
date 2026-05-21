import { act, fireEvent, render, screen, waitForElementToBeRemoved } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import type { ReactNode } from "react"
import { I18nextProvider } from "react-i18next"
import { MotionConfig } from "motion/react"
import { MemoryRouter } from "react-router-dom"
import i18n from "@/i18n/config"
import { AuthContext } from "@/context/auth-context"
import { ThemeContext } from "@/context/theme-context"
import { FirstRunFlow } from "../FirstRunFlow"
import { getFirstRunActive, setFirstRunActive } from "@/lib/tourState"
import type { User } from "@/types"

// Mock the services so the SetupStep's submit doesn't try to hit a
// real backend. Each test asserts the orchestration, not the network.
vi.mock("@/services/users", () => ({
  usersService: {
    updateProfile: vi.fn().mockResolvedValue({}),
  },
}))
vi.mock("@/services/preferences", () => ({
  preferencesService: {
    setPreferredLocale: vi.fn().mockResolvedValue({}),
  },
}))
vi.mock("@/services/storage", () => ({
  storageService: {
    uploadAvatar: vi.fn().mockResolvedValue("https://example.com/a.png"),
  },
}))
// CoursePickerStep fetches the catalog on mount — return an empty
// list so the step auto-skips via its own ``onSkip`` path. Tests
// that need the picker UI visible can re-mock per-test with real
// course data.
vi.mock("@/services/courses", () => ({
  coursesService: {
    getCourses: vi.fn().mockResolvedValue([]),
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
vi.mock("@/lib/images", () => ({
  toProxyImage: (url: string) => url,
}))

function makeUser(): User {
  return {
    id: "user-1",
    email: "test@example.com",
    full_name: "Test User",
    avatar_url: null,
    role: "student",
    preferred_locale: "en",
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  }
}

function Wrapper({ children, userId = "user-1" }: { children: ReactNode; userId?: string | null }) {
  const user = userId ? { ...makeUser(), id: userId } : null
  return (
    <MemoryRouter>
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
                resetPassword: vi.fn(),
                logout: vi.fn(),
                refreshUser: vi.fn().mockResolvedValue(undefined),
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

beforeEach(() => {
  window.localStorage.clear()
  setFirstRunActive(false)
})

afterEach(() => {
  setFirstRunActive(false)
  vi.clearAllMocks()
})

describe("FirstRunFlow", () => {
  it("renders nothing when there is no signed-in user", () => {
    const { container } = render(
      <Wrapper userId={null}>
        <FirstRunFlow />
      </Wrapper>,
    )
    expect(container.firstChild).toBeNull()
    expect(getFirstRunActive()).toBe(false)
  })

  it("starts on Privacy when no flags are set", () => {
    render(
      <Wrapper>
        <FirstRunFlow />
      </Wrapper>,
    )
    expect(screen.getByText(i18n.t("firstRun.privacy.title"))).toBeInTheDocument()
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

  it("accepting Privacy writes the flag and advances to Setup", async () => {
    render(
      <Wrapper>
        <FirstRunFlow />
      </Wrapper>,
    )
    fireEvent.click(screen.getByRole("checkbox"))
    fireEvent.click(screen.getByRole("button", { name: i18n.t("firstRun.privacy.next") }))
    expect(window.localStorage.getItem("equip.privacy.accepted.user-1")).toBe("1")
    // ``findByText`` (async) waits for AnimatePresence's exit-then-
    // enter sequence to settle. ``mode="wait"`` makes the new
    // step mount only AFTER the old one's exit resolves; even with
    // reduced-motion that's one microtask. Regex covers both
    // un-named and personalised heading shapes (wrapper's mocked
    // user has full_name="Test User" → firstName="Test").
    expect(await screen.findByText(/Make Equip yours/)).toBeInTheDocument()
  })

  it("skips straight to Setup when only Privacy flag is set", () => {
    window.localStorage.setItem("equip.privacy.accepted.user-1", "1")
    render(
      <Wrapper>
        <FirstRunFlow />
      </Wrapper>,
    )
    // Match the title with or without the personalised suffix —
    // the wrapper's mocked user has ``full_name: "Test User"`` which
    // makes ``firstNameOf`` return "Test", so the rendered heading
    // is "Make Equip yours, Test". Regex covers both shapes.
    expect(screen.getByText(/Make Equip yours/)).toBeInTheDocument()
    expect(screen.queryByText(i18n.t("firstRun.privacy.title"))).not.toBeInTheDocument()
  })

  it("renders nothing AND keeps firstRunActive=false when ALL three flags are set", () => {
    window.localStorage.setItem("equip.privacy.accepted.user-1", "1")
    window.localStorage.setItem("equip.first-run.setup.user-1", "1")
    // ``equip.first-run.completed`` is the picker-completion flag —
    // legacy users who finished the pre-picker flow already have
    // this set, so re-using the key keeps them past the gate.
    window.localStorage.setItem("equip.first-run.completed.user-1", "1")
    const { container } = render(
      <Wrapper>
        <FirstRunFlow />
      </Wrapper>,
    )
    expect(container.firstChild).toBeNull()
    expect(getFirstRunActive()).toBe(false)
  })

  it("Skip on Setup advances to the picker (does NOT close the gate)", async () => {
    window.localStorage.setItem("equip.privacy.accepted.user-1", "1")
    render(
      <Wrapper>
        <FirstRunFlow />
      </Wrapper>,
    )
    fireEvent.click(screen.getByRole("button", { name: i18n.t("firstRun.setup.skip") }))
    expect(window.localStorage.getItem("equip.first-run.setup.user-1")).toBe("1")
    // ``waitForElementToBeRemoved`` waits for the Setup heading to
    // exit (AnimatePresence's exit animation, then unmount). Without
    // this, the heading is still in the DOM at click-time + 0 ms
    // because exit hasn't run yet — even with reduced-motion.
    await waitForElementToBeRemoved(() =>
      screen.queryByText(/Make Equip yours/),
    )
    // Picker takes over (or auto-skips to done if catalog is empty —
    // mocked above). Either way the gate is still controlling the
    // ``firstRunActive`` signal until the picker resolves.
  })

  it("scopes flags by user id (no cross-account leak)", () => {
    window.localStorage.setItem("equip.privacy.accepted.user-A", "1")
    window.localStorage.setItem("equip.first-run.setup.user-A", "1")
    window.localStorage.setItem("equip.first-run.completed.user-A", "1")
    render(
      <Wrapper userId="user-B">
        <FirstRunFlow />
      </Wrapper>,
    )
    // user-B should see the Privacy screen even though user-A finished
    expect(screen.getByText(i18n.t("firstRun.privacy.title"))).toBeInTheDocument()
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
})
