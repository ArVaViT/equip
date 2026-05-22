import { useState } from "react"
import { useTranslation } from "react-i18next"
import { Globe } from "lucide-react"

import { Button } from "@/components/ui/button"
import { useAuth } from "@/context/useAuth"
import {
  SUPPORTED_LOCALES,
  isSupportedLocale,
  type SupportedLocale,
} from "@/i18n/config"
import { setDesiredLocale } from "@/i18n/useLocaleSync"
import { toast } from "@/lib/toast"
import { preferencesService } from "@/services/preferences"

interface LanguageSwitcherProps {
  /**
   * `compact` renders just the globe + a 2-letter chip — fits in the header
   * footprint. The default `full` variant shows full button labels and is
   * meant for the profile preferences card.
   */
  variant?: "compact" | "full"
}

const LABELS: Record<SupportedLocale, { native: string; short: string }> = {
  ru: { native: "Русский", short: "RU" },
  en: { native: "English", short: "EN" },
}

export default function LanguageSwitcher({ variant = "full" }: LanguageSwitcherProps) {
  const { i18n, t } = useTranslation()
  const { user, refreshUser } = useAuth()
  const [pending, setPending] = useState<SupportedLocale | null>(null)

  const active: SupportedLocale = isSupportedLocale(i18n.language) ? i18n.language : "ru"

  const switchTo = async (locale: SupportedLocale) => {
    if (locale === active || pending) return
    const previous = active
    setPending(locale)
    // Mark the desired locale BEFORE flipping i18n so the sync hook never
    // races with the auth profile while the PATCH is in flight.
    setDesiredLocale(locale)
    try {
      // Flip i18n immediately so the UI never lags behind a click. The
      // language-detector's `caches: ["localStorage"]` setting persists
      // the new value to localStorage on the `languageChanged` event,
      // so we don't write to localStorage manually.
      await i18n.changeLanguage(locale)
      if (user) {
        try {
          await preferencesService.setPreferredLocale(locale)
          // Once the profile reflects the new locale, the desired-guard
          // clears itself the next time `useLocaleSync` runs.
          await refreshUser()
        } catch {
          // PATCH failed: roll back UI + guard, and let the user know
          // their choice did not persist server-side.
          setDesiredLocale(null)
          await i18n.changeLanguage(previous)
          // Reuse the profile-update failure copy — saving a preference is
          // semantically a profile mutation, and this avoids touching the
          // locale JSON files (owned by other PRs running in parallel).
          toast({ title: t("profile.updateFailed"), variant: "destructive" })
        }
      } else {
        // Guests have no profile to reconcile against; clear the guard.
        setDesiredLocale(null)
      }
    } finally {
      setPending(null)
    }
  }

  if (variant === "compact") {
    const next: SupportedLocale = active === "ru" ? "en" : "ru"
    return (
      <Button
        variant="ghost"
        size="sm"
        className="h-8 w-8 p-0"
        onClick={() => switchTo(next)}
        disabled={pending !== null}
        aria-label={t("language.switchTo", { language: LABELS[next].native })}
        title={t("language.switchTo", { language: LABELS[next].native })}
      >
        <Globe className="h-4 w-4" strokeWidth={1.75} />
        <span className="sr-only">{LABELS[next].short}</span>
      </Button>
    )
  }

  return (
    <div className="flex items-center gap-2" role="radiogroup" aria-label={t("language.label")}>
      {SUPPORTED_LOCALES.map((locale) => (
        <Button
          key={locale}
          variant={locale === active ? "secondary" : "outline"}
          size="sm"
          role="radio"
          aria-checked={locale === active}
          onClick={() => switchTo(locale)}
          disabled={pending !== null}
        >
          {LABELS[locale].native}
        </Button>
      ))}
    </div>
  )
}
