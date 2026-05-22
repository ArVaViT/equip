import { driver, type Config, type DriveStep, type Driver } from "driver.js"
import "driver.js/dist/driver.css"
import "@/styles/editorial-tour.css"
import { sanitizeHtml } from "@/lib/sanitize"

export type TourStep = DriveStep

/**
 * driver.js writes ``popover.title`` and ``popover.description``
 * directly via ``innerHTML`` — confirmed in
 * ``node_modules/driver.js/dist/driver.js.iife.js``'s renderer.
 *
 * Today every tour string is a static translation with no user
 * interpolation, so there's no live XSS vector. But the moment
 * anyone adds ``t(KEY, { something: userInput })`` to a tour
 * step (a course title surfaced in a tour popover, a user name in
 * a header step, etc.), they'd silently open an XSS through the
 * popover — and our ``i18n/config.ts`` sets
 * ``interpolation.escapeValue = false`` which removes the only
 * other layer of protection.
 *
 * Hardening: run every tour string through the project's existing
 * DOMPurify config before driver.js gets to render it. This is the
 * same sanitiser ``ChapterView``'s rich-text blocks already use, so
 * a future tour string that legitimately needs ``<strong>`` or
 * ``<em>`` keeps those tags while ``<script>``, ``<img onerror>``,
 * ``href="javascript:..."`` etc. are stripped.
 */
function sanitiseStepTextInPlace(steps: readonly TourStep[]): TourStep[] {
  return steps.map((step) => {
    if (!step.popover) return step
    const { popover, ...rest } = step
    return {
      ...rest,
      popover: {
        ...popover,
        title: popover.title ? sanitizeHtml(popover.title) : popover.title,
        description: popover.description
          ? sanitizeHtml(popover.description)
          : popover.description,
      },
    }
  })
}

interface CreateTourOpts {
  steps: readonly TourStep[]
  /** Localised navigation copy. driver.js ships English-only and uses
   *  a different visual register from the rest of the app, so we
   *  override every label that ever shows on-screen. */
  labels: {
    next: string
    previous: string
    done: string
    /** Format string with literal ``{{current}}`` and ``{{total}}``
     *  placeholders that driver.js interpolates at render time. */
    progress: string
  }
  /** Fires when the user finishes the last step's "Done" click — the
   *  natural success signal for "they've actually seen the tour". */
  onDone?: () => void
  /** Fires when the user dismisses via X, Escape, or overlay click
   *  before the last step. Useful for distinguishing "skipped" vs
   *  "completed" in analytics or in persistence (a skip might still
   *  count as "they don't want this again"). */
  onSkipped?: () => void
}

/**
 * Read the current ``prefers-reduced-motion`` setting at call time.
 *
 * Honest fallback: ``window.matchMedia`` is missing in non-DOM
 * environments (SSR, vitest jsdom without the polyfill), so we treat
 * absence as "no preference" and let motion play. We re-read on every
 * tour construction rather than caching, so the OS-level setting
 * change reaches the next tour without a page reload.
 */
function reducedMotionPreferred(): boolean {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
    return false
  }
  try {
    return window.matchMedia("(prefers-reduced-motion: reduce)").matches
  } catch {
    return false
  }
}

/**
 * Build a driver.js tour with the editorial CSS class wired in and
 * localised navigation buttons.
 *
 * Callers should hold a single ``Driver`` instance per surface and
 * call ``.drive()`` to start, ``.destroy()`` to abort. The instance
 * is re-usable — re-calling ``drive()`` rewinds to step 0.
 *
 * We treat the "last step's Done click" as a separate event from
 * "user dismissed mid-tour" because, for persistence, both should
 * suppress the auto-fire next time, but for analytics they're
 * meaningfully different signals.
 */
export function createEditorialTour({
  steps,
  labels,
  onDone,
  onSkipped,
}: CreateTourOpts): Driver {
  // Track whether the user reached the end so onDestroyed can decide
  // which callback to fire. driver.js's own state.activeIndex isn't
  // reliable on the destroy hook — it gets reset before we see it.
  let reachedEnd = false
  const animate = !reducedMotionPreferred()

  const config: Config = {
    steps: sanitiseStepTextInPlace(steps) as DriveStep[],
    // Both the SVG stage morph and the popover fade are gated on this
    // single flag — driver.js doesn't expose them separately, and the
    // CSS media query catches the popover fade as a defense in depth.
    animate,
    smoothScroll: true,
    allowClose: true,
    // The spotlit element should READ as the subject of the popover,
    // not be a click-trap that scrolls the page underneath while the
    // user is reading. Without this, the catalog-search step would
    // accept keystrokes and reposition the spotlight on every char.
    disableActiveInteraction: true,
    overlayColor: "hsl(265 28% 13%)",
    overlayOpacity: 0.55,
    stagePadding: 6,
    stageRadius: 8,
    showProgress: steps.length > 1,
    progressText: labels.progress,
    nextBtnText: labels.next,
    prevBtnText: labels.previous,
    doneBtnText: labels.done,
    popoverClass: "editorial-tour-popover",
    onNextClick: (_el, _step, { state, driver: d }) => {
      // Last step's Next button doubles as Done — driver.js relabels
      // it via ``doneBtnText`` but still fires the same onNextClick.
      // Flag reachedEnd here so onDestroyed can distinguish a true
      // completion from an Esc/X/overlay dismissal.
      if (state.activeIndex !== undefined && state.activeIndex + 1 >= steps.length) {
        reachedEnd = true
      }
      d.moveNext()
    },
    onCloseClick: (_el, _step, { driver: d }) => {
      d.destroy()
    },
    onDestroyed: () => {
      if (reachedEnd) {
        onDone?.()
      } else {
        onSkipped?.()
      }
      // Reset for re-runs of the same instance.
      reachedEnd = false
    },
  }

  return driver(config)
}
