import { STUDENT_GRAND_TOUR_COVERS } from "./grandTourSteps"

/**
 * Shared in-memory signal: "is the grand tour currently scheduled or
 * actively running?". Per-page ``useUserTour`` hooks subscribe via
 * ``useSyncExternalStore`` and bail their own auto-start when this is
 * true AND their tour id is covered by the grand tour.
 *
 * Why module-level state instead of context: the grand tour mounts
 * inside ``AppRoutes`` (a parent of every page), but React effect
 * ordering runs CHILD effects before PARENT effects. So a per-page
 * tour's useEffect would have already scheduled its 350ms timer
 * before the grand tour's useEffect even runs. The only way to
 * cancel that timer retroactively is a reactive signal that flows
 * upward, which a module-level subscription provides without
 * threading context through.
 *
 * There's exactly one grand tour instance per app, so a single
 * module-level variable is safe (no multi-instance collisions).
 */

type Listener = () => void

const listeners = new Set<Listener>()
let _active = false

export function getGrandTourActive(): boolean {
  return _active
}

export function setGrandTourActive(next: boolean): void {
  if (_active === next) return
  _active = next
  listeners.forEach((cb) => cb())
}

export function subscribeGrandTour(cb: Listener): () => void {
  listeners.add(cb)
  return () => {
    listeners.delete(cb)
  }
}

const COVERED_SET = new Set<string>(STUDENT_GRAND_TOUR_COVERS)

export function isCoveredByGrandTour(tourId: string): boolean {
  return COVERED_SET.has(tourId)
}
