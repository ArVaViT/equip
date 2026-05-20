import { act, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import type { ReactNode } from "react"
import { I18nextProvider } from "react-i18next"
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
    <I18nextProvider i18n={i18n}>
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
    </I18nextProvider>
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

  it("accepting Privacy writes the flag and advances to Setup", () => {
    render(
      <Wrapper>
        <FirstRunFlow />
      </Wrapper>,
    )
    fireEvent.click(screen.getByRole("checkbox"))
    fireEvent.click(screen.getByRole("button", { name: i18n.t("firstRun.privacy.next") }))
    expect(window.localStorage.getItem("equip.privacy.accepted.user-1")).toBe("1")
    expect(screen.getByText(i18n.t("firstRun.setup.title"))).toBeInTheDocument()
  })

  it("skips straight to Setup when only Privacy flag is set", () => {
    window.localStorage.setItem("equip.privacy.accepted.user-1", "1")
    render(
      <Wrapper>
        <FirstRunFlow />
      </Wrapper>,
    )
    expect(screen.getByText(i18n.t("firstRun.setup.title"))).toBeInTheDocument()
    expect(screen.queryByText(i18n.t("firstRun.privacy.title"))).not.toBeInTheDocument()
  })

  it("renders nothing AND keeps firstRunActive=false when both flags are set", () => {
    window.localStorage.setItem("equip.privacy.accepted.user-1", "1")
    window.localStorage.setItem("equip.first-run.completed.user-1", "1")
    const { container } = render(
      <Wrapper>
        <FirstRunFlow />
      </Wrapper>,
    )
    expect(container.firstChild).toBeNull()
    expect(getFirstRunActive()).toBe(false)
  })

  it("Skip on Setup writes the completion flag and closes the flow", () => {
    window.localStorage.setItem("equip.privacy.accepted.user-1", "1")
    render(
      <Wrapper>
        <FirstRunFlow />
      </Wrapper>,
    )
    fireEvent.click(screen.getByRole("button", { name: i18n.t("firstRun.setup.skip") }))
    expect(window.localStorage.getItem("equip.first-run.completed.user-1")).toBe("1")
    expect(screen.queryByText(i18n.t("firstRun.setup.title"))).not.toBeInTheDocument()
    expect(getFirstRunActive()).toBe(false)
  })

  it("scopes flags by user id (no cross-account leak)", () => {
    window.localStorage.setItem("equip.privacy.accepted.user-A", "1")
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
