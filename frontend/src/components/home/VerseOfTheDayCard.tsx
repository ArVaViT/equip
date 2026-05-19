import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { BookOpenText } from "lucide-react"
import { Skeleton } from "@/components/ui/skeleton"
import {
  verseOfTheDayService,
  type VerseOfTheDay,
} from "@/services/verseOfTheDay"
import type { SupportedLocale } from "@/i18n/config"

/**
 * Daily devotional verse, fetched from the backend's curated rotation.
 *
 * Companion card to ``MyCoursesSection`` on the dashboard. Fails closed
 * — a non-200 from the backend (no API key configured, YouVersion
 * upstream blip) renders nothing rather than a broken card.
 *
 * Re-fetches whenever the active locale changes so the verse text and
 * reference label always match the rest of the UI.
 */
export function VerseOfTheDayCard() {
  const { t, i18n } = useTranslation()
  const locale = i18n.resolvedLanguage as SupportedLocale | undefined
  const [verse, setVerse] = useState<VerseOfTheDay | null>(null)
  const [loading, setLoading] = useState(true)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    if (!locale) return
    let cancelled = false
    setLoading(true)
    setFailed(false)
    verseOfTheDayService
      .get(locale)
      .then((data) => {
        if (cancelled) return
        setVerse(data)
      })
      .catch(() => {
        if (cancelled) return
        // Silent: the dashboard is more important than this card.
        setFailed(true)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [locale])

  if (failed) return null

  return (
    <section
      aria-labelledby="verse-of-the-day-heading"
      className="animate-fade-in flex h-full flex-col overflow-hidden rounded-md border border-border bg-card transition-[border-color] duration-300 hover:border-primary/25"
    >
      {/* Compact header to match MiniCalendar / MyCoursesSection rhythm on
          the dashboard side rail. Icon dropped from a framed 10×10 box to
          an inline 4×4 lucide — saves ~32px vertical, the difference
          between fitting and not fitting the single-viewport contract on
          a 13" laptop. */}
      <header className="flex items-center gap-2.5 border-b border-border bg-gradient-accent-subtle px-4 py-3 sm:px-5 sm:py-4">
        <BookOpenText
          className="h-4 w-4 shrink-0 text-muted-foreground"
          strokeWidth={1.75}
          aria-hidden
        />
        <div className="min-w-0">
          <p className="text-[10px] font-medium uppercase tracking-[0.18em] text-muted-foreground">
            {t("dashboard.votd.eyebrow")}
          </p>
          <h2
            id="verse-of-the-day-heading"
            className="font-serif text-sm font-semibold leading-tight tracking-tight text-foreground"
          >
            {t("dashboard.votd.title")}
          </h2>
        </div>
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-3 sm:px-5 sm:py-4">
        {loading || !verse ? (
          <div className="space-y-2">
            <Skeleton className="h-3.5 w-full" />
            <Skeleton className="h-3.5 w-11/12" />
            <Skeleton className="h-3.5 w-9/12" />
            <Skeleton className="mt-4 h-3 w-32" />
          </div>
        ) : (
          <figure className="space-y-2.5">
            <blockquote className="font-serif text-sm leading-relaxed text-foreground">
              &ldquo;{verse.text}&rdquo;
            </blockquote>
            <figcaption className="flex flex-wrap items-baseline gap-x-2 gap-y-1 text-xs text-muted-foreground">
              <cite className="not-italic font-medium text-foreground">{verse.reference}</cite>
              <span aria-hidden>·</span>
              <span>{verse.version}</span>
            </figcaption>
          </figure>
        )}
      </div>
    </section>
  )
}
