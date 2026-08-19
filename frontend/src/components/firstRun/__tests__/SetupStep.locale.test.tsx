/**
 * The language a brand-new account is handed on its very first screen.
 *
 * This is the one that cost a German reader their language. They read the
 * whole landing page in German, signed up with Google — which carries no
 * language into the signup trigger, so the profile was created with the
 * fallback ``ru`` and ``locale_source: "default"`` — and Quick Setup then
 * seeded itself from that column. Russian arrived pre-selected, and both
 * exits made it permanent: Submit PATCHed it as a chosen preference, Skip
 * "restored" it over the German on screen.
 *
 * So the assertions here are about a profile value nobody chose never being
 * treated as a choice, on either exit.
 */

import { act, render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import type { ReactNode } from "react"
import { I18nextProvider } from "react-i18next"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import i18n, { DEFAULT_LOCALE } from "@/i18n/config"
import { AuthContext } from "@/context/auth-context"
import { ThemeContext } from "@/context/theme-context"
import type { User } from "@/types"

const setPreferredLocale = vi.fn().mockResolvedValue({})
vi.mock("@/services/preferences", () => ({
  preferencesService: {
    setPreferredLocale: (locale: string) => setPreferredLocale(locale),
    reportDetectedLocale: vi.fn().mockResolvedValue({}),
  },
}))
vi.mock("@/services/users", () => ({
  usersService: { updateProfile: vi.fn().mockResolvedValue({}) },
}))
vi.mock("@/services/storage", () => ({
  storageService: { uploadAvatar: vi.fn().mockResolvedValue("") },
}))
vi.mock("@/lib/toast", () => ({ toast: vi.fn() }))
vi.mock("@/lib/images", () => ({ toProxyImage: (url: string) => url }))

import { SetupStep } from "../SetupStep"
import { initialSetupLocale } from "../setupLocale"

function makeUser(overrides: Partial<User> = {}): User {
  return {
    id: "user-1",
    email: "a@b.com",
    full_name: "A",
    avatar_url: null,
    role: "student",
    preferred_locale: "ru",
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  }
}

function Wrapper({ children, user }: { children: ReactNode; user: User }) {
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
            applyUser: vi.fn(),
          }}
        >
          {children}
        </AuthContext.Provider>
      </ThemeContext.Provider>
    </I18nextProvider>
  )
}

describe("initialSetupLocale", () => {
  it("takes a language the person actually chose", () => {
    expect(initialSetupLocale(makeUser({ preferred_locale: "uk", locale_source: "chosen" }), "de")).toBe("uk")
  })

  it("takes a language the server merely detected — it is still about them", () => {
    expect(initialSetupLocale(makeUser({ preferred_locale: "de", locale_source: "detected" }), "en")).toBe("de")
  })

  it("skips a column value nobody chose and keeps the language on screen", () => {
    // The Google-signup shape: "ru" in the column, "default" in the source.
    expect(initialSetupLocale(makeUser({ preferred_locale: "ru", locale_source: "default" }), "de")).toBe("de")
  })

  it("reads a missing locale_source as chosen, never as default", () => {
    // An older server that does not send the field: refusing to guess is the
    // safe reading — a real preference must not be overwritten.
    expect(initialSetupLocale(makeUser({ preferred_locale: "uk" }), "de")).toBe("uk")
  })

  it("ignores a locale the app does not serve", () => {
    const stranger = makeUser({ preferred_locale: "fr" as User["preferred_locale"], locale_source: "chosen" })
    expect(initialSetupLocale(stranger, "de")).toBe("de")
    expect(initialSetupLocale(stranger, "fr")).toBe(DEFAULT_LOCALE)
  })

  it("falls back to the project default when nothing is known", () => {
    expect(initialSetupLocale(null, undefined)).toBe(DEFAULT_LOCALE)
  })
})

describe("SetupStep, for an account whose language nobody chose", () => {
  beforeEach(async () => {
    setPreferredLocale.mockClear()
    await act(async () => {
      await i18n.changeLanguage("de")
    })
  })

  afterEach(async () => {
    await act(async () => {
      await i18n.changeLanguage("en")
    })
  })

  it("pre-selects the language the reader is actually reading", () => {
    render(
      <Wrapper user={makeUser({ preferred_locale: "ru", locale_source: "default" })}>
        <SetupStep onComplete={vi.fn()} onSkip={vi.fn()} />
      </Wrapper>,
    )

    expect(screen.getByRole("button", { name: /Deutsch/ })).toHaveAttribute("aria-pressed", "true")
    expect(screen.getByRole("button", { name: /Русский/ })).toHaveAttribute("aria-pressed", "false")
  })

  it("submits the language on screen, not the one the column happened to hold", async () => {
    const user = userEvent.setup()
    const onComplete = vi.fn()
    render(
      <Wrapper user={makeUser({ preferred_locale: "ru", locale_source: "default" })}>
        <SetupStep onComplete={onComplete} onSkip={vi.fn()} />
      </Wrapper>,
    )

    await user.click(screen.getByRole("button", { name: i18n.t("firstRun.setup.submit") }))

    expect(setPreferredLocale).toHaveBeenCalledWith("de")
    expect(onComplete).toHaveBeenCalled()
  })

  it("leaves the language alone on Skip", async () => {
    const user = userEvent.setup()
    const onSkip = vi.fn()
    render(
      <Wrapper user={makeUser({ preferred_locale: "ru", locale_source: "default" })}>
        <SetupStep onComplete={vi.fn()} onSkip={onSkip} />
      </Wrapper>,
    )

    await user.click(screen.getByRole("button", { name: i18n.t("firstRun.setup.skip") }))

    expect(onSkip).toHaveBeenCalled()
    expect(setPreferredLocale).not.toHaveBeenCalled()
    // Skipping is "change nothing" — it must not be a way to end up in a
    // language the reader never saw.
    expect(i18n.resolvedLanguage).toBe("de")
  })

  it("still honours a real preference over the browser", () => {
    render(
      <Wrapper user={makeUser({ preferred_locale: "uk", locale_source: "chosen" })}>
        <SetupStep onComplete={vi.fn()} onSkip={vi.fn()} />
      </Wrapper>,
    )

    expect(screen.getByRole("button", { name: /Українська/ })).toHaveAttribute("aria-pressed", "true")
  })
})
