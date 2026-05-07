import type { ReactNode } from "react"
import { render, screen, waitFor, act } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { I18nextProvider } from "react-i18next"
import { beforeEach, afterEach, describe, expect, it, vi } from "vitest"
import i18n from "@/i18n/config"
import type { User } from "@/types"

// Mocks must be declared before importing the SUT.
const setPreferredLocale = vi.fn()
vi.mock("@/services/preferences", () => ({
  preferencesService: {
    setPreferredLocale: (...a: unknown[]) => setPreferredLocale(...a),
  },
}))

const toast = vi.fn()
vi.mock("@/lib/toast", () => ({
  toast: (...a: unknown[]) => toast(...a),
}))

// Stand-in auth context. The real provider depends on Supabase + Datadog; the
// switcher only reads `user` and `refreshUser`, so a fake provider keeps this
// test small and deterministic.
type AuthState = { user: User | null; refreshUser: () => Promise<void> }
let authState: AuthState = { user: null, refreshUser: vi.fn().mockResolvedValue(undefined) }
vi.mock("@/context/useAuth", () => ({
  useAuth: () => authState,
}))

import LanguageSwitcher from "../LanguageSwitcher"
import { setDesiredLocale, getDesiredLocale } from "@/i18n/useLocaleSync"

function makeUser(overrides: Partial<User> = {}): User {
  return {
    id: "user-1",
    email: "a@b.com",
    full_name: "A",
    avatar_url: null,
    role: "student",
    preferred_locale: "ru",
    created_at: "2024-01-01T00:00:00Z",
    updated_at: "2024-01-01T00:00:00Z",
    ...overrides,
  }
}

function I18nWrapper({ children }: { children: ReactNode }) {
  return <I18nextProvider i18n={i18n}>{children}</I18nextProvider>
}

describe("LanguageSwitcher", () => {
  beforeEach(async () => {
    setPreferredLocale.mockReset()
    toast.mockReset()
    authState = {
      user: makeUser(),
      refreshUser: vi.fn().mockResolvedValue(undefined),
    }
    setDesiredLocale(null)
    await act(async () => {
      await i18n.changeLanguage("ru")
    })
  })

  afterEach(() => {
    setDesiredLocale(null)
  })

  it("flips the UI optimistically and persists via the preferences API on success", async () => {
    setPreferredLocale.mockResolvedValue(makeUser({ preferred_locale: "en" }))
    const user = userEvent.setup()

    render(<LanguageSwitcher variant="compact" />, { wrapper: I18nWrapper })

    const button = screen.getByRole("button")
    await user.click(button)

    await waitFor(() => {
      expect(setPreferredLocale).toHaveBeenCalledWith("en")
    })
    expect(i18n.language).toBe("en")
    expect(toast).not.toHaveBeenCalled()
    expect(authState.refreshUser).toHaveBeenCalledTimes(1)
  })

  it("rolls the UI back and toasts when the PATCH fails (race fix)", async () => {
    setPreferredLocale.mockRejectedValue(new Error("network down"))
    const user = userEvent.setup()

    render(<LanguageSwitcher variant="compact" />, { wrapper: I18nWrapper })

    const button = screen.getByRole("button")
    await user.click(button)

    await waitFor(() => {
      expect(setPreferredLocale).toHaveBeenCalledWith("en")
    })
    // i18n was rolled back to the previous locale.
    expect(i18n.language).toBe("ru")
    // The desired-locale guard was cleared so the sync hook can run normally.
    expect(getDesiredLocale()).toBeNull()
    // refreshUser must NOT be called on failure — that would re-trigger the
    // sync hook with the stale profile.
    expect(authState.refreshUser).not.toHaveBeenCalled()
    // The user gets a destructive toast about the failed save.
    expect(toast).toHaveBeenCalledTimes(1)
    expect(toast).toHaveBeenCalledWith(
      expect.objectContaining({ variant: "destructive" }),
    )
  })

  it("sets the desired-locale guard before flipping i18n so useLocaleSync can no-op", async () => {
    // Slow-resolve PATCH so we can observe the in-flight state.
    let resolvePatch: ((v: unknown) => void) | null = null
    setPreferredLocale.mockReturnValue(
      new Promise((resolve) => {
        resolvePatch = resolve as (v: unknown) => void
      }),
    )
    const user = userEvent.setup()

    render(<LanguageSwitcher variant="compact" />, { wrapper: I18nWrapper })

    const button = screen.getByRole("button")
    // userEvent's promise won't resolve until the PATCH does, so fire and
    // assert without awaiting the click.
    void user.click(button)

    await waitFor(() => {
      expect(getDesiredLocale()).toBe("en")
    })
    expect(i18n.language).toBe("en")

    // Resolve the PATCH; refreshUser is invoked, and the guard clears once
    // the profile is in sync (handled inside useLocaleSync's effect — here
    // we just confirm the switcher's contract: it left the guard set).
    await act(async () => {
      resolvePatch!(makeUser({ preferred_locale: "en" }))
    })
    await waitFor(() => {
      expect(authState.refreshUser).toHaveBeenCalledTimes(1)
    })
  })

  it("does not call the preferences API for guests", async () => {
    authState = {
      user: null,
      refreshUser: vi.fn().mockResolvedValue(undefined),
    }
    const user = userEvent.setup()

    render(<LanguageSwitcher variant="compact" />, { wrapper: I18nWrapper })

    await user.click(screen.getByRole("button"))

    expect(setPreferredLocale).not.toHaveBeenCalled()
    expect(i18n.language).toBe("en")
    expect(getDesiredLocale()).toBeNull()
  })
})
