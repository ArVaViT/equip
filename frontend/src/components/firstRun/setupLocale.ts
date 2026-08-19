import { DEFAULT_LOCALE, isSupportedLocale, type SupportedLocale } from "@/i18n/config"
import type { User } from "@/types"

/**
 * Which language Quick Setup opens on — and why it is not simply the
 * profile's.
 *
 * ``profiles.preferred_locale`` is NOT NULL, so every account has one from
 * the moment it exists. A Google sign-up carries no language into the signup
 * trigger, so those accounts get the fallback ``ru`` with
 * ``locale_source = "default"`` — a value nobody chose. Seeding the screen
 * from it pre-selected Russian for a German who had just read the whole
 * landing page in German, and then both exits made it stick: Submit PATCHed
 * that "choice" as a real preference, and Skip "restored" it over the German
 * the reader was actually looking at. One click, permanently Russian, on the
 * very first screen after joining.
 *
 * So the profile only counts when somebody actually chose it. When the
 * server says nobody did, the language the visitor is reading right now is
 * the honest answer — the same rung of the precedence rule ``useLocaleSync``
 * applies (and the value it is busy reporting back to the server as
 * detected).
 *
 * Its own module rather than a helper inside ``SetupStep.tsx`` so the file
 * keeps exporting only components (Fast Refresh) and so the rule can be
 * tested without mounting anything.
 */
export function initialSetupLocale(
  user: Pick<User, "preferred_locale" | "locale_source"> | null | undefined,
  detected: string | undefined,
): SupportedLocale {
  if (user && user.locale_source !== "default" && isSupportedLocale(user.preferred_locale)) {
    return user.preferred_locale
  }
  if (isSupportedLocale(detected)) return detected
  // Last rung of the precedence rule. Practically unreachable — i18next has
  // always resolved a language by the time this screen mounts — but the
  // ``ru`` here is the same ``ru`` the rest of the stack falls back to,
  // rather than the ``en`` this line used to guess at.
  return DEFAULT_LOCALE
}
