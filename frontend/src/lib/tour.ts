import { driver, type Config, type DriveStep, type Driver } from "driver.js"
import "driver.js/dist/driver.css"
import "@/styles/editorial-tour.css"

export type TourStep = DriveStep

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

  const config: Config = {
    steps: steps as DriveStep[],
    animate: true,
    smoothScroll: true,
    allowClose: true,
    overlayColor: "hsl(var(--foreground))",
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
