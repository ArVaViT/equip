import { act, render } from "@testing-library/react"
import { I18nextProvider } from "react-i18next"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import i18n from "@/i18n/config"
import type { User } from "@/types"

const applyUser = vi.fn()
let authState: { user: User | null; applyUser: (u: User) => void } = {
  user: null,
  applyUser: (u: User) => applyUser(u),
}
vi.mock("@/context/useAuth", () => ({
  useAuth: () => authState,
}))

// The real endpoint answers with the profile as it now stands: the
// reported language, and ``locale_source`` moved off "default" so the hook
// never reports it a second time.
const reportDetectedLocale = vi.fn((locale: string) =>
  Promise.resolve(
    makeUser({ preferred_locale: locale as User["preferred_locale"], locale_source: "detected" }),
  ),
)
vi.mock("@/services/preferences", () => ({
  preferencesService: {
    reportDetectedLocale: (locale: string) => reportDetectedLocale(locale),
    setPreferredLocale: vi.fn(),
  },
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
    reportDetectedLocale.mockClear()
    applyUser.mockClear()
    await act(async () => {
      await i18n.changeLanguage("ru")
    })
    authState = { user: null, applyUser: (u: User) => applyUser(u) }
  })

  afterEach(() => {
    setDesiredLocale(null)
  })

  it("syncs i18n to the profile's preferred_locale on login", async () => {
    authState = { ...authState, user: makeUser({ preferred_locale: "en" }) }

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
    authState = { ...authState, user: makeUser({ preferred_locale: "ru" }) }

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
    authState = { ...authState, user: makeUser({ preferred_locale: "en" }) }

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
      ...authState,
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

  describe("a profile language nobody chose", () => {
    it("does not overwrite the language the visitor was already reading", async () => {
      // The scenario this exists for: a German reads the landing page in
      // German, signs in with Google — which carries no language into the
      // signup trigger — and the profile is created with the fallback
      // locale. Before this, the first thing the product did after they
      // joined was switch them to Russian.
      await act(async () => {
        await i18n.changeLanguage("de")
      })
      authState = {
        ...authState,
        user: makeUser({ preferred_locale: "ru", locale_source: "default" }),
      }

      await act(async () => {
        render(
          <I18nextProvider i18n={i18n}>
            <Probe />
          </I18nextProvider>,
        )
      })

      expect(i18n.language).toBe("de")
    })

    it("reports the browser's language back so the profile stops guessing", async () => {
      await act(async () => {
        await i18n.changeLanguage("de")
      })
      authState = {
        ...authState,
        user: makeUser({ preferred_locale: "ru", locale_source: "default" }),
      }

      await act(async () => {
        render(
          <I18nextProvider i18n={i18n}>
            <Probe />
          </I18nextProvider>,
        )
      })

      expect(reportDetectedLocale).toHaveBeenCalledWith("de")
    })

    it("applies the profile the server sends back instead of discarding it", async () => {
      // The PATCH answers with the profile as it now stands — German,
      // ``locale_source: "detected"``. Throwing that away left every other
      // consumer reading the stale "ru / default", and the first-run setup
      // screen decides which language to pre-select from exactly those two
      // fields.
      await act(async () => {
        await i18n.changeLanguage("de")
      })
      authState = {
        ...authState,
        user: makeUser({ preferred_locale: "ru", locale_source: "default" }),
      }

      await act(async () => {
        render(
          <I18nextProvider i18n={i18n}>
            <Probe />
          </I18nextProvider>,
        )
      })

      expect(applyUser).toHaveBeenCalledTimes(1)
      expect(applyUser).toHaveBeenCalledWith(
        expect.objectContaining({ preferred_locale: "de", locale_source: "detected" }),
      )
    })

    it("leaves a chosen language alone", async () => {
      // The other half of the rule: a real preference outranks the
      // browser, which is what the profile was always meant to mean.
      await act(async () => {
        await i18n.changeLanguage("de")
      })
      authState = {
        ...authState,
        user: makeUser({ preferred_locale: "uk", locale_source: "chosen" }),
      }

      await act(async () => {
        render(
          <I18nextProvider i18n={i18n}>
            <Probe />
          </I18nextProvider>,
        )
      })

      expect(i18n.language).toBe("uk")
      expect(reportDetectedLocale).not.toHaveBeenCalled()
    })
  })
})
