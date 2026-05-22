import { act, render } from "@testing-library/react"
import { I18nextProvider } from "react-i18next"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import i18n from "@/i18n/config"
import type { User } from "@/types"

let authState: { user: User | null } = { user: null }
vi.mock("@/context/useAuth", () => ({
  useAuth: () => authState,
}))

import { useLocaleSync, setDesiredLocale, getDesiredLocale } from "../useLocaleSync"

function Probe() {
  useLocaleSync()
  return null
}

function makeUser(overrides: Partial<User> = {}): User {
  return {
    id: "u1",
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

describe("useLocaleSync", () => {
  beforeEach(async () => {
    setDesiredLocale(null)
    await act(async () => {
      await i18n.changeLanguage("ru")
    })
    authState = { user: null }
  })

  afterEach(() => {
    setDesiredLocale(null)
  })

  it("syncs i18n to the profile's preferred_locale on login", async () => {
    authState = { user: makeUser({ preferred_locale: "en" }) }

    await act(async () => {
      render(
        <I18nextProvider i18n={i18n}>
          <Probe />
        </I18nextProvider>,
      )
    })

    expect(i18n.language).toBe("en")
  })

  it("ignores a stale profile while a switch is in flight (race fix)", async () => {
    // Simulate the LanguageSwitcher having just flipped to "en" and called
    // setDesiredLocale("en") — but the auth profile still says "ru" because
    // the PATCH hasn't landed yet.
    await act(async () => {
      await i18n.changeLanguage("en")
    })
    setDesiredLocale("en")
    authState = { user: makeUser({ preferred_locale: "ru" }) }

    await act(async () => {
      render(
        <I18nextProvider i18n={i18n}>
          <Probe />
        </I18nextProvider>,
      )
    })

    // Without the guard, the hook would have flipped i18n back to "ru" and
    // silently undone the user's choice. The guard prevents that.
    expect(i18n.language).toBe("en")
    expect(getDesiredLocale()).toBe("en")
  })

  it("clears the desired-locale guard once the profile catches up", async () => {
    await act(async () => {
      await i18n.changeLanguage("en")
    })
    setDesiredLocale("en")
    // Profile now matches the desired locale (PATCH succeeded + refresh ran).
    authState = { user: makeUser({ preferred_locale: "en" }) }

    await act(async () => {
      render(
        <I18nextProvider i18n={i18n}>
          <Probe />
        </I18nextProvider>,
      )
    })

    expect(i18n.language).toBe("en")
    expect(getDesiredLocale()).toBeNull()
  })

  it("ignores unsupported preferred_locale values", async () => {
    authState = {
      user: makeUser({ preferred_locale: "fr" as unknown as User["preferred_locale"] }),
    }

    await act(async () => {
      render(
        <I18nextProvider i18n={i18n}>
          <Probe />
        </I18nextProvider>,
      )
    })

    expect(i18n.language).toBe("ru")
  })
})
