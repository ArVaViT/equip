import { driver, type Config, type Driver, type DriveStep } from "driver.js"
import "driver.js/dist/driver.css"
import "@/styles/editorial-tour.css"

/**
 * A grand-tour step is a regular driver.js step plus an optional
 * ``route``. When ``route`` is set and differs from the current URL,
 * the orchestrator navigates to it via React Router and waits for
 * the step's ``element`` selector to render before highlighting.
 *
 * Closing-summary steps with no element and no route render as a
 * centered popover wherever the user happens to be — same fallback
 * driver.js uses natively for element-less steps.
 */
export interface GrandTourStep extends DriveStep {
  route?: string
}

interface CreateGrandTourOpts {
  steps: readonly GrandTourStep[]
  labels: {
    next: string
    previous: string
    done: string
    progress: string
  }
  /** Navigate fn from React Router — passed in so the orchestrator
   *  doesn't have to import router internals or be mounted inside a
   *  Route. */
  navigate: (path: string) => void
  /** Current path read at construction; the orchestrator compares
   *  against ``window.location.pathname`` at click-time, but the
   *  initial check uses this snapshot. */
  initialPath: string
  /** Reduced-motion respect — passed in so the same hook decision
   *  applies to both the popover fade AND the SVG stage morph. */
  reducedMotion: boolean
  onDone?: () => void
  onSkipped?: () => void
}

/**
 * Wait for a CSS selector to appear in the DOM, up to ``timeoutMs``.
 *
 * Used after navigation: React mounts the new route asynchronously,
 * and the step's spotlight target may not be in the tree yet. We
 * watch ``document.body`` for additions and resolve as soon as the
 * selector finds a match. Times out gracefully — if the element
 * never appears, driver.js renders a centered popover with no
 * spotlight, which is acceptable degraded behaviour.
 *
 * The selector is queried up-front so a step whose target was
 * already in the tree at navigation time resolves synchronously.
 */
export function waitForSelector(selector: string, timeoutMs = 5000): Promise<Element | null> {
  if (typeof document === "undefined") return Promise.resolve(null)
  const existing = document.querySelector(selector)
  if (existing) return Promise.resolve(existing)
  return new Promise((resolve) => {
    let resolved = false
    const observer = new MutationObserver(() => {
      const el = document.querySelector(selector)
      if (el && !resolved) {
        resolved = true
        observer.disconnect()
        window.clearTimeout(timer)
        resolve(el)
      }
    })
    observer.observe(document.body, { childList: true, subtree: true })
    const timer = window.setTimeout(() => {
      if (resolved) return
      resolved = true
      observer.disconnect()
      resolve(null)
    }, timeoutMs)
  })
}

/**
 * Build an orchestrated multi-route tour.
 *
 * driver.js natively assumes all steps live on one page. The
 * orchestrator wraps it: each ``onNextClick`` / ``onPrevClick``
 * checks whether the upcoming step lives on a different route, and
 * if so navigates first, awaits the target element, then calls
 * ``driver.moveNext()`` / ``driver.movePrevious()``.
 *
 * The driver instance owns the popover and overlay; the orchestrator
 * just decides when to advance and what to wait for.
 */
export function createGrandTour({
  steps,
  labels,
  navigate,
  initialPath,
  reducedMotion,
  onDone,
  onSkipped,
}: CreateGrandTourOpts): Driver {
  let reachedEnd = false
  let destroyed = false

  // Driver.js types want a mutable DriveStep[]; the route field is
  // ours and gets read separately from the array index inside the
  // navigation hooks below.
  const baseSteps: DriveStep[] = steps.map((s) => ({
    element: s.element,
    popover: s.popover,
  }))

  // Pre-position on the first step's route so the very first
  // spotlight lands on a settled target. The hook below handles
  // subsequent transitions.
  const firstRoute = steps[0]?.route
  if (firstRoute && firstRoute !== initialPath) {
    navigate(firstRoute)
  }

  const advanceTo = async (
    targetIdx: number,
    d: Driver,
    move: "next" | "prev",
  ) => {
    if (destroyed) return
    if (targetIdx < 0 || targetIdx >= steps.length) {
      // Out of bounds = end of tour. Let driver handle (it'll fire
      // onDestroyed).
      if (move === "next") d.moveNext()
      else d.movePrevious()
      return
    }
    const target = steps[targetIdx]
    if (!target) return
    const currentPath = window.location.pathname
    if (target.route && target.route !== currentPath) {
      navigate(target.route)
      if (target.element) {
        const selector =
          typeof target.element === "string" ? target.element : null
        if (selector) await waitForSelector(selector)
      } else {
        // Centered popover step still needs a short tick so the
        // route's new tree exists before driver.js re-measures.
        await new Promise<void>((r) => window.setTimeout(r, 80))
      }
    }
    if (destroyed) return
    if (move === "next") d.moveNext()
    else d.movePrevious()
  }

  const config: Config = {
    steps: baseSteps,
    animate: !reducedMotion,
    smoothScroll: true,
    allowClose: true,
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
      const currentIdx = state.activeIndex ?? 0
      const nextIdx = currentIdx + 1
      if (nextIdx >= steps.length) {
        reachedEnd = true
        d.moveNext()
        return
      }
      void advanceTo(nextIdx, d, "next")
    },
    onPrevClick: (_el, _step, { state, driver: d }) => {
      const currentIdx = state.activeIndex ?? 0
      const prevIdx = currentIdx - 1
      if (prevIdx < 0) {
        d.movePrevious()
        return
      }
      void advanceTo(prevIdx, d, "prev")
    },
    onCloseClick: (_el, _step, { driver: d }) => {
      d.destroy()
    },
    onDestroyed: () => {
      destroyed = true
      if (reachedEnd) onDone?.()
      else onSkipped?.()
      reachedEnd = false
    },
  }

  return driver(config)
}
