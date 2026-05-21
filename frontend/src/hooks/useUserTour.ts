import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react"
import { useTranslation } from "react-i18next"
import type { Driver } from "driver.js"
import { createEditorialTour, type TourStep } from "@/lib/tour"
import { useAuth } from "@/context/useAuth"
import {
  getFirstRunActive,
  getGrandTourActive,
  isCoveredByGrandTour,
  subscribeFirstRun,
  subscribeGrandTour,
} from "@/lib/tourState"

interface UseUserTourOpts {
  /** Stable identifier for this surface's tour. Combined with the
   *  current user id to form the localStorage flag, so different
   *  accounts on a shared device each get their own first-run. */
  tourId: string
  /** Steps to drive. The hook reads these on every call — pass a
   *  memoised array if you need referential stability. */
  steps: readonly TourStep[]
  /** When ``true`` (the default) and the user hasn't seen this tour,
   *  start it automatically once on mount. Pass ``false`` for tours
   *  that should only open via a manual "Take a tour" trigger. */
  autoStart?: boolean
  /** Optional gate for data-dependent pages: hold the auto-start
   *  until this becomes ``true``. ``undefined`` is treated as "ready
   *  immediately"; passing a literal ``false`` blocks. Lets a page
   *  block the spotlight until its tour targets actually render. */
  ready?: boolean
  /** Roles that should never see auto-started tours. Admins are the
   *  obvious skip: they're power users who built the surfaces and
   *  don't need the orientation. Manual ``start()`` is still allowed
   *  so an admin can preview the tour if they want. */
  skipRoles?: ReadonlyArray<string>
  /** Delay before auto-firing (lets the surrounding UI mount and
   *  layout so the spotlight lands on a settled target). */
  autoStartDelayMs?: number
}

interface UseUserTourReturn {
  /** Programmatically open the tour from step 0. Bypasses every
   *  gate — alreadySeen, skipRoles, ready. The trigger source is
   *  always intentional (a "Take a tour" click). */
  start: () => void
  /** Whether the persistence flag for (user, tourId) is already set.
   *  Surfaces can use this to hide a "Take a tour" trigger after the
   *  user has seen it once, or to keep it visible — either is a
   *  defensible product call. */
  alreadySeen: boolean
}

const STORAGE_PREFIX = "equip.tour.seen"
const DEFAULT_SKIP_ROLES: ReadonlyArray<string> = ["admin"]

function flagKey(userId: string | undefined, tourId: string): string | null {
  if (!userId) return null
  return `${STORAGE_PREFIX}.${userId}.${tourId}`
}

function readSeen(userId: string | undefined, tourId: string): boolean {
  const key = flagKey(userId, tourId)
  if (!key || typeof window === "undefined") return false
  try {
    return window.localStorage.getItem(key) === "1"
  } catch {
    return false
  }
}

function writeSeen(userId: string | undefined, tourId: string): void {
  const key = flagKey(userId, tourId)
  if (!key || typeof window === "undefined") return
  try {
    window.localStorage.setItem(key, "1")
  } catch {
    // Private-browsing or quota — the tour will re-offer next visit.
  }
}

/**
 * React hook that wires up an editorial driver.js tour with per-user
 * "have they seen it yet?" persistence.
 *
 * Persistence is keyed by ``(userId, tourId)`` so a second account on
 * the same device gets its own first-run; logged-out callers see no
 * tour and no flag is written.
 *
 * Auto-starts by default for non-admin users on their first visit
 * to each surface. Both completing the tour ("Done") and dismissing
 * it ("X" / Esc / overlay click) write the flag — the assumption is
 * "user has been exposed to this once, don't pester them again". A
 * manual ``start()`` call from a "Take a tour" trigger always opens
 * the tour regardless of the flag, so the user can re-watch on
 * demand. Manual start also cancels any pending auto-start timer so
 * the user doesn't see a brief double-fire if they click within the
 * autoStartDelayMs window.
 */
export function useUserTour({
  tourId,
  steps,
  autoStart = true,
  ready,
  skipRoles = DEFAULT_SKIP_ROLES,
  autoStartDelayMs = 350,
}: UseUserTourOpts): UseUserTourReturn {
  const { user } = useAuth()
  const { t } = useTranslation()
  const driverRef = useRef<Driver | null>(null)
  const firedRef = useRef(false)
  const timerRef = useRef<number | null>(null)
  const stepsRef = useRef(steps)
  useEffect(() => {
    stepsRef.current = steps
  }, [steps])

  const userId = user?.id
  const userRole = user?.role
  // Reactive grand-tour signal — declared first so it can feed the
  // ``alreadySeen`` resync effect below.
  const grandTourActive = useSyncExternalStore(
    subscribeGrandTour,
    getGrandTourActive,
    () => false,
  )
  const isCovered = isCoveredByGrandTour(tourId)
  // ``alreadySeen`` is read once into state on mount instead of every
  // render. Without this, every keystroke / sort change on a
  // tour-hosting page (gradebook, etc.) would hit
  // ``window.localStorage.getItem`` synchronously on the render path.
  // The ``userId``/``tourId`` change re-reads via the effect below.
  const [alreadySeen, setAlreadySeen] = useState(() => readSeen(userId, tourId))
  useEffect(() => {
    setAlreadySeen(readSeen(userId, tourId))
    // ``grandTourActive`` IS in the deps too: when the grand tour
    // finishes (flips the signal false), its ``onDone``/``onSkipped``
    // also writes per-page seen flags via
    // ``suppressCoveredPerPageTours``. Without this resync, a
    // dashboard hook that has been mounted through the whole grand
    // tour keeps its stale ``alreadySeen=false`` state and fires its
    // own 5-step tour 350 ms after the grand tour ends — which is
    // exactly the "another 5 steps after 10" symptom the user
    // reported. Re-reading on the signal flip picks up the fresh
    // suppression flag.
  }, [userId, tourId, grandTourActive])

  // Reactive first-run signal: while the Privacy Policy + Quick Setup
  // screens are up, EVERY per-page tour bails (covered or not). The
  // user is in the middle of configuring their account; popping a
  // spotlight underneath the modal would be confusing.
  const firstRunActive = useSyncExternalStore(
    subscribeFirstRun,
    getFirstRunActive,
    () => false,
  )

  const buildDriver = useCallback((): Driver => {
    return createEditorialTour({
      steps: stepsRef.current,
      labels: {
        next: t("tour.next"),
        previous: t("tour.previous"),
        done: t("tour.done"),
        progress: t("tour.progress", {
          // Pass literal placeholders back through i18next so driver.js
          // can do its own substitution at render time.
          current: "{{current}}",
          total: "{{total}}",
        }),
      },
      onDone: () => writeSeen(userId, tourId),
      onSkipped: () => writeSeen(userId, tourId),
    })
  }, [t, tourId, userId])

  const start = useCallback(() => {
    // Manual start counts as "fired" — block any pending auto-start
    // timer AND mark the surface as fired so the auto effect can't
    // re-trigger after the user has already opened the tour by hand.
    firedRef.current = true
    if (timerRef.current !== null) {
      window.clearTimeout(timerRef.current)
      timerRef.current = null
    }
    // Always rebuild — labels depend on the active i18n language, and
    // a stale Driver from a previous locale would render English
    // buttons on a Russian session (or vice versa).
    driverRef.current?.destroy()
    driverRef.current = buildDriver()
    driverRef.current.drive()
  }, [buildDriver])

  useEffect(() => {
    if (firedRef.current) return
    if (!autoStart) return
    if (!userId) return
    if (alreadySeen) return
    if (steps.length === 0) return
    if (userRole && skipRoles.includes(userRole)) return
    // ``ready === false`` is the only blocking value. ``undefined``
    // means "no gate" and lets the tour fire immediately.
    if (ready === false) return
    // First-run flow (Privacy + Setup) blocks every per-page tour
    // unconditionally — the user is configuring their account, no
    // spotlights underneath the modal.
    if (firstRunActive) return
    // Grand tour wins races with its covered surfaces. If it's
    // pending (scheduled) or actively running, the per-page tour for
    // a covered surface stands down. Once the grand tour finishes,
    // ``alreadySeen`` will be true on the next mount.
    if (grandTourActive && isCovered) return

    // ``firedRef`` is set INSIDE the timer callback, not here. If we
    // set it synchronously and a dep flips (e.g. ``firstRunActive``
    // false → true mid-mount), the cleanup cancels the pending timer
    // but ``firedRef`` would stay true forever — the tour would
    // never re-fire when conditions become favourable again. By
    // deferring the flag-set to the callback, a cancelled-and-never-
    // fired timer leaves ``firedRef=false`` so the next dep change
    // can re-schedule cleanly. The flag still flips synchronously
    // inside manual ``start()``.
    timerRef.current = window.setTimeout(() => {
      timerRef.current = null
      firedRef.current = true
      start()
    }, autoStartDelayMs)
    return () => {
      if (timerRef.current !== null) {
        window.clearTimeout(timerRef.current)
        timerRef.current = null
      }
    }
    // ``alreadySeen``, ``grandTourActive``, ``firstRunActive`` IN
    // deps so a mid-mount state change (e.g. grand tour or first-run
    // fires after this hook has already run its first effect pass)
    // re-runs the early-return chain and cancels any pending timer
    // via the cleanup.
  }, [autoStart, autoStartDelayMs, userId, userRole, ready, steps.length, alreadySeen, grandTourActive, isCovered, firstRunActive, skipRoles, start])

  // Defense in depth: if the grand tour or first-run flow activates
  // while this hook's tour is already on screen, tear it down to
  // make room. Doesn't fire on initial render thanks to the
  // driverRef null-check.
  useEffect(() => {
    const shouldTearDown =
      (grandTourActive && isCovered) || firstRunActive
    if (shouldTearDown && driverRef.current) {
      driverRef.current.destroy()
      driverRef.current = null
    }
  }, [grandTourActive, isCovered, firstRunActive])

  useEffect(() => {
    return () => {
      driverRef.current?.destroy()
      driverRef.current = null
      if (timerRef.current !== null) {
        window.clearTimeout(timerRef.current)
        timerRef.current = null
      }
    }
  }, [])

  return { start, alreadySeen }
}
