import type { SupportedLocale } from "@/i18n/config"
import { createContext } from "react"
import type { User } from "@/types"

export interface AuthContextValue {
  user: User | null
  loading: boolean
  login: (email: string, password: string) => Promise<void>
  register: (
    email: string,
    password: string,
    fullName: string,
    preferredLocale: SupportedLocale,
  ) => Promise<void>
  signInWithGoogle: () => Promise<void>
  resetPassword: (email: string) => Promise<void>
  logout: () => Promise<void>
  refreshUser: () => Promise<void>
  /**
   * Swap in a profile the caller already holds, without a round trip.
   *
   * Some endpoints answer with the refreshed profile — ``PATCH
   * /users/me/preferences`` does. Throwing that away and leaving the cached
   * ``user`` stale is not free: ``useLocaleSync`` reports a detected locale
   * and the server replies "preferred_locale=de, locale_source=detected",
   * but every other consumer kept reading "ru / default" until the next
   * ``refreshUser`` — including the first-run setup screen, which decides
   * which language to pre-select from exactly those two fields.
   *
   * Ignores a profile for anybody but the currently signed-in user, so a
   * response that lands after a logout or an account switch cannot resurrect
   * the previous session.
   */
  applyUser: (user: User) => void
}

export const AuthContext = createContext<AuthContextValue | null>(null)
