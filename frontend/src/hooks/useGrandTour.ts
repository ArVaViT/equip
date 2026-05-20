import { useCallback, useEffect, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { useNavigate, useLocation } from "react-router-dom"
import type { Driver } from "driver.js"
import { useAuth } from "@/context/useAuth"
import { createGrandTour } from "@/lib/grandTour"
import { STUDENT_GRAND_TOUR_COVERS, studentGrandTourSteps } from "@/lib/grandTourSteps"
import { setGrandTourActive } from "@/lib/tourState"

const STORAGE_PREFIX_GRAND = "equip.grand-tour.seen"
const STORAGE_PREFIX_PERPAGE = "equip.tour.seen"
const AUTO_START_DELAY_MS = 500

function grandFlagKey(userId: string | undefined): string | null {
  if (!userId) return null
  return `${STORAGE_PREFIX_GRAND}.${userId}`
}

function readGrandSeen(userId: string | undefined): boolean {
  const key = grandFlagKey(userId)
  if (!key || typeof window === "undefined") return false
  try {
    return window.localStorage.getItem(key) === "1"
  } catch {
    return false
  }
}

function writeGrandSeen(userId: string | undefined): void {
  const key = grandFlagKey(userId)
  if (!key || typeof window === "undefined") return
  try {
    window.localStorage.setItem(key, "1")
  } catch {
    /* private browsing */
  }
}

/**
 * Mark every per-page tour the grand tour covers as ``seen`` so the
 * user doesn't get a second wave of contextual tours on the same
 * surfaces immediately after the grand tour ends. Per-page tours on
 * surfaces NOT covered (chapter view, course editor, etc.) still
 * fire on first visit — that's the desired layering.
 */
function suppressCoveredPerPageTours(userId: string | undefined): void {
  if (!userId || typeof window === "undefined") return
  for (const tourId of STUDENT_GRAND_TOUR_COVERS) {
    try {
      window.localStorage.setItem(`${STORAGE_PREFIX_PERPAGE}.${userId}.${tourId}`, "1")
    } catch {
      /* ignore */
    }
  }
}

function reducedMotionPreferred(): boolean {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") return false
  try {
    return window.matchMedia("(prefers-reduced-motion: reduce)").matches
  } catch {
    return false
  }
}

interface UseGrandTourReturn {
  /** Programmatic start — bypasses persistence and role gates. Used
   *  for a future "Replay grand tour" trigger if we ever add one to
   *  the welcome card. */
  start: () => void
  alreadySeen: boolean
}

/**
 * App-root hook that owns the cross-page grand tour.
 *
 * Auto-fires once per (userId) on first login when:
 *   - user is signed in
 *   - user is a student (admins skip; teachers get per-page tours
 *     because their journey requires dynamic course ids)
 *   - the ``equip.grand-tour.seen.{userId}`` flag is missing
 *   - the current route is the dashboard (``/``) — we don't yank a
 *     user off their current page into a tour
 *
 * On completion or dismissal:
 *   - writes the grand-tour seen flag
 *   - writes ``seen`` flags for every per-page tour the grand tour
 *     covers, so revisiting those surfaces doesn't fire a second
 *     wave of contextual tours
 *
 * Mount this hook ONCE inside ``App`` (after AuthProvider, inside
 * BrowserRouter). Mounting in multiple places will create multiple
 * driver instances racing each other.
 */
export function useGrandTour(): UseGrandTourReturn {
  const { user } = useAuth()
  const { t } = useTranslation()
  const navigate = useNavigate()
  const location = useLocation()
  const driverRef = useRef<Driver | null>(null)
  const firedRef = useRef(false)
  const timerRef = useRef<number | null>(null)

  const userId = user?.id
  const userRole = user?.role

  const [alreadySeen, setAlreadySeen] = useState(() => readGrandSeen(userId))
  useEffect(() => {
    setAlreadySeen(readGrandSeen(userId))
  }, [userId])

  const buildAndDrive = useCallback(() => {
    if (!userId) return
    const steps = studentGrandTourSteps(t)
    driverRef.current?.destroy()
    driverRef.current = createGrandTour({
      steps,
      labels: {
        next: t("tour.next"),
        previous: t("tour.previous"),
        done: t("tour.done"),
        progress: t("tour.progress", { current: "{{current}}", total: "{{total}}" }),
      },
      navigate,
      initialPath: location.pathname,
      reducedMotion: reducedMotionPreferred(),
      onDone: () => {
        writeGrandSeen(userId)
        suppressCoveredPerPageTours(userId)
        setAlreadySeen(true)
        setGrandTourActive(false)
      },
      onSkipped: () => {
        // Dismissal still counts — user has been exposed; don't pester
        // them again. Same semantics as the per-page tours.
        writeGrandSeen(userId)
        suppressCoveredPerPageTours(userId)
        setAlreadySeen(true)
        setGrandTourActive(false)
      },
    })
    driverRef.current.drive()
  }, [t, userId, navigate, location.pathname])

  const start = useCallback(() => {
    firedRef.current = true
    if (timerRef.current !== null) {
      window.clearTimeout(timerRef.current)
      timerRef.current = null
    }
    buildAndDrive()
  }, [buildAndDrive])

  useEffect(() => {
    if (firedRef.current) return
    if (!userId) return
    if (alreadySeen) return
    if (userRole && userRole !== "student") return
    // Only kick off when we're already on the dashboard. A user
    // landing on ``/courses/:id`` from a shared link shouldn't get
    // teleported home for an orientation tour. The first surface the
    // student typically lands on after sign-in is ``/`` so this
    // covers the happy path.
    if (location.pathname !== "/") return

    firedRef.current = true
    // Flag "grand tour is taking the wheel" SYNCHRONOUSLY here, even
    // though the tour itself doesn't fire until after the timeout.
    // Per-page useUserTour hooks subscribe to this signal and bail
    // their own auto-starts before they get a chance to race the
    // grand tour during the 500ms window.
    setGrandTourActive(true)
    timerRef.current = window.setTimeout(buildAndDrive, AUTO_START_DELAY_MS)
    return () => {
      if (timerRef.current !== null) {
        window.clearTimeout(timerRef.current)
        timerRef.current = null
      }
    }
  }, [userId, userRole, alreadySeen, location.pathname, buildAndDrive])

  useEffect(() => {
    return () => {
      driverRef.current?.destroy()
      driverRef.current = null
      if (timerRef.current !== null) {
        window.clearTimeout(timerRef.current)
        timerRef.current = null
      }
      // Reset shared signal on unmount so per-page tours can fire on
      // the next mount cycle if the user signs back in.
      setGrandTourActive(false)
    }
  }, [])

  return { start, alreadySeen }
}
