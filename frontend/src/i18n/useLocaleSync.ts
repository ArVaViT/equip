import { useEffect } from "react"
import { useTranslation } from "react-i18next"

import { useAuth } from "@/context/useAuth"
import { preferencesService } from "@/services/preferences"

import { isSupportedLocale, type SupportedLocale } from "./config"

/**
 * Module-level "pending desired locale" guard.
 *
 * `LanguageSwitcher` updates this *before* it flips i18n optimistically and
 * fires the `PATCH /users/me/preferences` request. While it's set, the sync
 * hook below treats it as the source of truth and refuses to "correct" the
 * UI back to the (still-stale) profile value. Once the profile catches up
 * (or the switcher rolls back on failure), the guard is cleared.
 *
 * This is module-level on purpose: the switcher and the sync hook live in
 * different parts of the tree but share a single i18n instance, so a single
 * shared mutable cell is the simplest correct coordination.
 */
let desiredLocale: SupportedLocale | null = null

export function setDesiredLocale(locale: SupportedLocale | null): void {
  desiredLocale = locale
}

export function getDesiredLocale(): SupportedLocale | null {
  return desiredLocale
}

/**
 * Keep i18next and the authenticated profile in lockstep.
 *
 * - On login: profile.preferred_locale wins. We update i18n; the
 *   `i18next-browser-languagedetector` cache (configured with
 *   `caches: ["localStorage"]` in `config.ts`) writes the value to
 *   localStorage automatically on `languageChanged`, so a refresh picks
 *   the same value before the auth context has a chance to load.
 * - For guests: we leave i18next's detector alone (browser → localStorage
 *   fallback already runs at init time).
 * - During an in-flight `LanguageSwitcher` PATCH: the `desiredLocale` guard
 *   makes us a no-op so we don't fight the optimistic update.
 *
 * Mounted once in `App` near the auth provider.
 */
export function useLocaleSync(): void {
  const { user, applyUser } = useAuth()
  const { i18n } = useTranslation()

  useEffect(() => {
    if (!user) return
    const profileLocale = user.preferred_locale
    if (!isSupportedLocale(profileLocale)) return

    // The profile has a language nobody ever chose.
    //
    // ``preferred_locale`` is NOT NULL, so every account has one from the
    // moment it exists — including accounts created by a Google sign-in,
    // which carries no language into the signup trigger and lands on the
    // fallback. Treating that as a preference is how a German who read
    // the whole landing page in German got Russian handed to them one
    // second after joining: the profile is the source of truth, and the
    // profile said Russian.
    //
    // So when the server says nobody chose it, the browser wins, and we
    // tell the server what the browser said. It records it as detected —
    // still yielding to any real choice made later.
    if (user.locale_source === "default") {
      const detected = i18n.resolvedLanguage ?? i18n.language
      if (isSupportedLocale(detected)) {
        void preferencesService.reportDetectedLocale(detected).then(
          (updated) => {
            // The response is the profile the server now holds —
            // ``preferred_locale`` the browser's language,
            // ``locale_source`` "detected". Dropping it left the cached
            // profile still saying "ru / default" until some unrelated
            // ``refreshUser``, and the cached profile is what the rest of
            // the app reads: the first-run setup screen picks the language
            // to pre-select from exactly these two fields, so it went on
            // offering Russian to the German this branch had just rescued.
            applyUser(updated)
          },
          () => {
            // Nothing to recover: the UI is already in the right language,
            // and the next load reports it again.
          },
        )
      }
      return
    }

    // A switch is in progress and the profile hasn't caught up yet — defer.
    if (desiredLocale !== null && desiredLocale !== profileLocale) return
    // Profile now matches the user's pending desire (PATCH succeeded and the
    // refresh landed). Drop the guard so future profile changes win normally.
    if (desiredLocale === profileLocale) {
      desiredLocale = null
    }

    if (i18n.language === profileLocale) return
    void i18n.changeLanguage(profileLocale)
    // Keying on ``user?.preferred_locale`` (not the whole ``user``)
    // means a Supabase ``TOKEN_REFRESHED`` rewrite of the user
    // object doesn't re-trigger the locale-sync work — the locale
    // hasn't actually changed. Login (undefined → "ru") and a
    // PreferencesService PATCH ("ru" → "en") both still flow.
    // ``locale_source`` joins the deps because the profile can move from
    // "nobody chose this" to "detected" without the locale itself
    // changing, and the effect must not keep re-reporting after that.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.preferred_locale, user?.locale_source, i18n, applyUser])
}
