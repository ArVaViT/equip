import { useCallback, useEffect, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import type { Driver } from "driver.js"
import { createEditorialTour, type TourStep } from "@/lib/tour"
import { useAuth } from "@/context/useAuth"

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
  // ``alreadySeen`` is read once into state on mount instead of every
  // render. Without this, every keystroke / sort change on a
  // tour-hosting page (gradebook, etc.) would hit
  // ``window.localStorage.getItem`` synchronously on the render path.
  // The ``userId`` change re-reads (different account, possibly
  // different flag) via the effect below.
  const [alreadySeen, setAlreadySeen] = useState(() => readSeen(userId, tourId))
  useEffect(() => {
    setAlreadySeen(readSeen(userId, tourId))
  }, [userId, tourId])

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

    firedRef.current = true
    timerRef.current = window.setTimeout(start, autoStartDelayMs)
    return () => {
      if (timerRef.current !== null) {
        window.clearTimeout(timerRef.current)
        timerRef.current = null
      }
    }
    // ``alreadySeen`` IS in deps (unlike before) because we now keep
    // it in state — a flag write from another tab via storage event
    // would still not invalidate, but the in-tab user-id swap that
    // also re-reads the flag now properly re-evaluates.
  }, [autoStart, autoStartDelayMs, userId, userRole, ready, steps.length, alreadySeen, skipRoles, start])

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
