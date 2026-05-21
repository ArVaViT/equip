import { STUDENT_GRAND_TOUR_COVERS } from "./grandTourSteps"

/**
 * Shared in-memory signals for the onboarding flow:
 *
 *   ``firstRunActive``  — Privacy Policy + Quick Setup screens are up.
 *                          Blocks the grand tour AND every per-page
 *                          tour so the user can finish their setup
 *                          without anything overlapping.
 *
 *   ``grandTourActive`` — Cross-page grand tour is scheduled or
 *                          running. Blocks per-page tours on the
 *                          surfaces the grand tour covers.
 *
 * Per-page ``useUserTour`` hooks subscribe via ``useSyncExternalStore``
 * to BOTH signals — they bail their auto-start if either is true (and
 * the tour id is covered, for the grand-tour case).
 *
 * Why module-level state instead of context: the orchestrators
 * (FirstRunFlow, useGrandTour) mount inside ``AppRoutes`` which is
 * the parent of every page, but React effect ordering runs CHILD
 * effects before PARENT effects. So a per-page tour's useEffect
 * would have already scheduled its 350 ms timer before the parent's
 * useEffect even runs. The only way to cancel that timer
 * retroactively is a reactive signal that flows upward, which a
 * module-level subscription provides without threading context.
 *
 * There's exactly one of each orchestrator per app, so single
 * module-level variables are safe (no multi-instance collisions).
 */

type Listener = () => void

const grandListeners = new Set<Listener>()
const firstRunListeners = new Set<Listener>()
let _grandTourActive = false
let _firstRunActive = false

// ───── Grand tour signal ─────────────────────────────────────────

export function getGrandTourActive(): boolean {
  return _grandTourActive
}

export function setGrandTourActive(next: boolean): void {
  if (_grandTourActive === next) return
  _grandTourActive = next
  grandListeners.forEach((cb) => cb())
}

export function subscribeGrandTour(cb: Listener): () => void {
  grandListeners.add(cb)
  return () => {
    grandListeners.delete(cb)
  }
}

// ───── First-run signal ──────────────────────────────────────────

export function getFirstRunActive(): boolean {
  return _firstRunActive
}

export function setFirstRunActive(next: boolean): void {
  if (_firstRunActive === next) return
  _firstRunActive = next
  firstRunListeners.forEach((cb) => cb())
}

export function subscribeFirstRun(cb: Listener): () => void {
  firstRunListeners.add(cb)
  return () => {
    firstRunListeners.delete(cb)
  }
}

// ───── Coverage map ──────────────────────────────────────────────

const COVERED_SET = new Set<string>(STUDENT_GRAND_TOUR_COVERS)

export function isCoveredByGrandTour(tourId: string): boolean {
  return COVERED_SET.has(tourId)
}
