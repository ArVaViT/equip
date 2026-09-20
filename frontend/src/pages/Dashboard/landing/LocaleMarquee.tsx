import { useReducedMotion } from "motion/react"

import { LOCALE_NATIVE_LABELS, SUPPORTED_LOCALES } from "@/i18n/config"

/**
 * A running line of the four languages, endlessly.
 *
 * Vadym asked for a marquee of testimonials and said outright that they
 * would be invented — «я знаю они будт фек но это маркетинг» — and offered
 * the alternative himself: «ну или бегущую строку с чем-то другим». This is
 * that alternative. Fabricated praise on a Bible-study platform costs
 * exactly the thing the platform is selling, and the first reader who asks
 * «кто это сказал?» finds out. When real students say something worth
 * quoting, a testimonial strip can replace this in an afternoon.
 *
 * The languages are the honest version of the same idea: the strongest
 * claim Equip can make about itself, stated by demonstration rather than by
 * adjective, and already shown working in the tour above — one lesson,
 * four languages, switched on screen. Each label is written in its own
 * language, which is the whole point; «Ukrainian» in English proves nothing
 * that «Українська» does not prove better.
 *
 * MECHANICS. Two identical runs sit side by side and the pair slides left
 * by exactly half its width, so the moment the first run leaves the frame
 * the second is precisely where it started — a seam nobody can catch. The
 * CSS lives in `index.css` as `@keyframes marquee`, because a transform
 * animation this simple has no business holding a JS frame loop open for
 * the life of the page.
 *
 * Paused on hover, so a reader can actually look at it, and not rendered at
 * all under `prefers-reduced-motion` — an endlessly moving band is the
 * clearest case there is for that preference.
 */
export function LocaleMarquee() {
  const prefersReducedMotion = useReducedMotion()

  const labels = SUPPORTED_LOCALES.map((locale) => LOCALE_NATIVE_LABELS[locale])

  if (prefersReducedMotion) {
    return (
      <section className="border-y border-line py-8" aria-hidden>
        <p className="mx-auto flex max-w-5xl flex-wrap justify-center gap-x-10 gap-y-3 px-4 font-serif text-2xl text-ink-muted">
          {labels.map((label) => (
            <span key={label}>{label}</span>
          ))}
        </p>
      </section>
    )
  }

  const run = (
    <ul className="flex shrink-0 items-center gap-12 pr-12" aria-hidden>
      {labels.map((label) => (
        <li key={label} className="flex items-center gap-12 whitespace-nowrap">
          <span className="font-serif text-3xl text-ink sm:text-5xl">{label}</span>
          <span className="text-2xl text-line" aria-hidden>
            ·
          </span>
        </li>
      ))}
    </ul>
  )

  return (
    <section className="group overflow-hidden border-y border-line py-8" aria-hidden>
      <div className="flex w-max animate-marquee group-hover:[animation-play-state:paused]">
        {run}
        {run}
      </div>
    </section>
  )
}
