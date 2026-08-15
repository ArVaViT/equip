import { useState } from "react"
import { useTranslation } from "react-i18next"
import { Globe, Loader2 } from "lucide-react"

import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { useAuth } from "@/context/useAuth"
import {
  DEFAULT_LOCALE,
  LOCALE_NATIVE_LABELS,
  SUPPORTED_LOCALES,
  isSupportedLocale,
  type SupportedLocale,
} from "@/i18n/config"
import { setDesiredLocale } from "@/i18n/useLocaleSync"
import { toast } from "@/lib/toast"
import { preferencesService } from "@/services/preferences"

interface LanguageSwitcherProps {
  /**
   * `compact` renders the globe with the two-letter code — for the header,
   * where horizontal space is the scarce thing. `full` puts the language's
   * own name on the trigger, for the profile preferences card.
   */
  variant?: "compact" | "full"
}

/**
 * One control for however many languages the platform serves.
 *
 * It was a row of buttons, one per language. That reads fine at two and
 * survives four; at seven it is a wall of chips competing with the rest of
 * the page, and every new language re-lays out whatever sits beside it. A
 * menu costs one click and stops caring how long the list gets — which is
 * the shape to be in before the fifth language, not after it.
 *
 * Each language is named in itself (Deutsch, not "German"), because the
 * person looking for their own language is, by definition, reading in a
 * language they may not know.
 */
export default function LanguageSwitcher({ variant = "full" }: LanguageSwitcherProps) {
  const { i18n, t } = useTranslation()
  const { user, refreshUser } = useAuth()
  const [pending, setPending] = useState<SupportedLocale | null>(null)

  const active: SupportedLocale = isSupportedLocale(i18n.language) ? i18n.language : DEFAULT_LOCALE

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

  const busy = pending !== null

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant={variant === "compact" ? "ghost" : "outline"}
          size="sm"
          className={variant === "compact" ? "h-8 gap-1.5 px-2" : "gap-2"}
          disabled={busy}
          aria-label={t("language.label")}
          title={t("language.label")}
        >
          {busy ? (
            <Loader2 className="h-4 w-4 animate-spin" strokeWidth={1.75} aria-hidden />
          ) : (
            <Globe className="h-4 w-4" strokeWidth={1.75} aria-hidden />
          )}
          <span>{variant === "compact" ? active.toUpperCase() : LOCALE_NATIVE_LABELS[active]}</span>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="min-w-[11rem]">
        <DropdownMenuRadioGroup
          value={active}
          onValueChange={(value) => {
            if (isSupportedLocale(value)) void switchTo(value)
          }}
        >
          {SUPPORTED_LOCALES.map((locale) => (
            <DropdownMenuRadioItem key={locale} value={locale} disabled={busy}>
              <span className="flex-1">{LOCALE_NATIVE_LABELS[locale]}</span>
              <span className="text-xs uppercase text-ink-muted">{locale}</span>
            </DropdownMenuRadioItem>
          ))}
        </DropdownMenuRadioGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
