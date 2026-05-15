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
      className="animate-fade-in mb-12 overflow-hidden rounded-md border border-border bg-card transition-[border-color] duration-300 hover:border-primary/25"
    >
      <header className="border-b border-border bg-gradient-accent-subtle px-5 py-6 sm:px-6">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md border border-border/80 bg-card">
            <BookOpenText
              className="h-5 w-5 text-muted-foreground"
              strokeWidth={1.75}
              aria-hidden
            />
          </div>
          <div className="min-w-0">
            <p className="text-xs font-medium uppercase tracking-[0.18em] text-muted-foreground">
              {t("home.votd.eyebrow")}
            </p>
            <h2
              id="verse-of-the-day-heading"
              className="font-serif text-lg font-semibold leading-tight tracking-tight text-foreground"
            >
              {t("home.votd.title")}
            </h2>
          </div>
        </div>
      </header>

      <div className="px-5 py-6 sm:px-6">
        {loading || !verse ? (
          <div className="space-y-3">
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-11/12" />
            <Skeleton className="h-4 w-9/12" />
            <Skeleton className="mt-5 h-3 w-32" />
          </div>
        ) : (
          <figure className="space-y-4">
            <blockquote className="font-serif text-base leading-relaxed text-foreground sm:text-lg">
              &ldquo;{verse.text}&rdquo;
            </blockquote>
            <figcaption className="flex flex-wrap items-baseline gap-x-2 gap-y-1 text-sm text-muted-foreground sm:text-xs">
              <cite className="not-italic font-medium text-foreground">
                {verse.reference}
              </cite>
              <span aria-hidden>·</span>
              <span>{verse.version}</span>
            </figcaption>
          </figure>
        )}
      </div>
    </section>
  )
}
