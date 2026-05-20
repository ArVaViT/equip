import { useCallback, useEffect, useRef } from "react"
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
  /** When ``true`` and the user hasn't seen this tour, start it
   *  automatically once on mount. The auto-fire never re-triggers on
   *  later mounts after the persistence flag is set. */
  autoStartIfFirstTime?: boolean
  /** Delay before auto-firing (lets the surrounding UI mount and
   *  layout so the spotlight lands on a settled target). */
  autoStartDelayMs?: number
}

interface UseUserTourReturn {
  /** Programmatically open the tour from step 0. */
  start: () => void
  /** Whether the persistence flag for (user, tourId) is already set.
   *  Surfaces can use this to hide a "Take a tour" trigger after the
   *  user has seen it once, or to keep it visible — either is a
   *  defensible product call. */
  alreadySeen: boolean
}

const STORAGE_PREFIX = "equip.tour.seen"

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
 * Both completing the tour ("Done") and dismissing it ("X" / Esc /
 * overlay click) write the flag — the assumption is "user has been
 * exposed to this once, don't pester them again". A manual ``start()``
 * call from a "Take a tour" trigger always opens the tour regardless
 * of the flag, so the user can re-watch on demand.
 */
export function useUserTour({
  tourId,
  steps,
  autoStartIfFirstTime = false,
  autoStartDelayMs = 250,
}: UseUserTourOpts): UseUserTourReturn {
  const { user } = useAuth()
  const { t } = useTranslation()
  const driverRef = useRef<Driver | null>(null)
  const stepsRef = useRef(steps)
  useEffect(() => {
    stepsRef.current = steps
  }, [steps])

  const userId = user?.id
  const alreadySeen = readSeen(userId, tourId)

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
    // Always rebuild — labels depend on the active i18n language, and
    // a stale Driver from a previous locale would render English
    // buttons on a Russian session (or vice versa).
    driverRef.current?.destroy()
    driverRef.current = buildDriver()
    driverRef.current.drive()
  }, [buildDriver])

  useEffect(() => {
    if (!autoStartIfFirstTime) return
    if (!userId) return
    if (alreadySeen) return
    if (steps.length === 0) return

    const timer = window.setTimeout(start, autoStartDelayMs)
    return () => window.clearTimeout(timer)
    // ``alreadySeen`` is a one-shot read at mount; deliberately not in
    // deps so a localStorage write mid-render doesn't restart the
    // tour. ``steps.length`` covers the late-arriving-targets case.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoStartIfFirstTime, autoStartDelayMs, userId, steps.length, start])

  useEffect(() => {
    return () => {
      driverRef.current?.destroy()
      driverRef.current = null
    }
  }, [])

  return { start, alreadySeen }
}
