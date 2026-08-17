import api from "./api"
import type { SupportedLocale } from "@/i18n/config"
import type { User } from "@/types"

/**
 * Persist user preferences server-side.
 *
 * Wraps the FastAPI `PATCH /users/me/preferences` endpoint. Returns the
 * refreshed user profile so the caller can update its local cache without a
 * second round-trip.
 */
export const preferencesService = {
  async setPreferredLocale(locale: SupportedLocale): Promise<User> {
    const { data } = await api.patch<User>("/users/me/preferences", {
      preferred_locale: locale,
    })
    return data
  },

  /**
   * Tell the server what the browser asked for, for an account that was
   * never asked.
   *
   * A Google sign-up carries no language into the signup trigger, so the
   * profile is created with the fallback locale no matter what the person
   * was reading a second earlier. `detected: true` marks this as a report
   * rather than a decision: the server records it, and refuses it outright
   * if the account already has a language somebody picked.
   */
  async reportDetectedLocale(locale: SupportedLocale): Promise<User> {
    const { data } = await api.patch<User>("/users/me/preferences", {
      preferred_locale: locale,
      detected: true,
    })
    return data
  },
}
