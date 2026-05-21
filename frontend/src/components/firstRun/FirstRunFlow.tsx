import { useCallback, useEffect, useRef, useState } from "react"
import { AnimatePresence, motion, useReducedMotion } from "motion/react"
import { useNavigate } from "react-router-dom"
import { useAuth } from "@/context/useAuth"
import { setFirstRunActive } from "@/lib/tourState"
import type { Course } from "@/types"
import { PrivacyPolicyStep } from "./PrivacyPolicyStep"
import { SetupStep } from "./SetupStep"
import { CoursePickerStep } from "./CoursePickerStep"
import { EnrollSplash } from "./EnrollSplash"
import { firstNameOf } from "@/lib/names"

const EDITORIAL_EASE: [number, number, number, number] = [0.22, 1, 0.36, 1]

/** CSS selector for elements eligible for the focus trap. Mirrors
 *  the WAI-ARIA "tabbable elements" definition without depending on
 *  a focus-trap library — same shape used by Radix UI internally. */
const FOCUSABLE_SELECTOR =
  'a[href], button:not([disabled]), input:not([disabled]):not([type="hidden"]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'

import {
  firstRunPickerKey,
  firstRunSetupKey,
  grandTourSeenKey,
  privacyAcceptedKey,
} from "@/lib/storageKeys"

function readFlag(key: string): boolean {
  if (typeof window === "undefined") return false
  try {
    return window.localStorage.getItem(key) === "1"
  } catch {
    return false
  }
}

function writeFlag(key: string): void {
  if (typeof window === "undefined") return
  try {
    window.localStorage.setItem(key, "1")
  } catch {
    /* private browsing — the gate will fire again next visit */
  }
}

type Step = "privacy" | "setup" | "picker" | "splash" | "done"

function decideInitialStep(userId: string | undefined): Step {
  if (!userId) return "done"
  if (!readFlag(privacyAcceptedKey(userId))) return "privacy"
  if (!readFlag(firstRunSetupKey(userId))) return "setup"
  if (!readFlag(firstRunPickerKey(userId))) return "picker"
  return "done"
}

/**
 * Full-screen first-run orchestrator: Privacy Policy → Quick Setup
 * → done.
 *
 * Rendered above everything else (z-index above the grand tour
 * overlay's 1000000000) so it blocks all interaction until the user
 * either accepts privacy + completes/skips setup, or closes the
 * browser. Persistence is per-user-id ``localStorage``, scoped so a
 * shared device's second account still gets its own first run.
 *
 * Signals to the ``tourState`` module while it's mounted so the grand
 * tour and every per-page tour bail their own auto-starts. They
 * resume the moment this component unmounts.
 *
 * Mount once inside ``AppRoutes`` (after AuthProvider) — see
 * ``App.tsx``. Mounting in multiple places will race the modal stack.
 */
export function FirstRunFlow() {
  const { user } = useAuth()
  const navigate = useNavigate()
  const prefersReducedMotion = useReducedMotion()
  const userId = user?.id
  const firstName = firstNameOf(user?.full_name)
  const dialogRef = useRef<HTMLDivElement>(null)
  // ``useState`` initialiser runs once per mount; ``userId`` change
  // (sign-in, account switch) re-derives via the effect below.
  const [step, setStep] = useState<Step>(() => decideInitialStep(userId))
  // The course the user enrolled in via the picker. Drives the
  // EnrollSplash celebration and the post-splash navigation. We
  // keep it as state (not a ref) so the splash re-renders on
  // ``setStep("splash")`` with the freshest value.
  const [enrolledCourse, setEnrolledCourse] = useState<Course | null>(null)

  useEffect(() => {
    setStep(decideInitialStep(userId))
  }, [userId])

  // Autofocus the first focusable element on each step transition so
  // keyboard users land inside the dialog. Otherwise focus stays on
  // ``<body>`` and Tab walks into the hidden page underneath.
  useEffect(() => {
    if (step === "done") return
    const root = dialogRef.current
    if (!root) return
    // ``requestAnimationFrame`` instead of immediate query so React's
    // commit has settled and the focusable elements actually exist.
    // We yield to a step-specific autofocus (e.g. ``SetupStep``
    // focuses its name input) by skipping if focus is already
    // inside the dialog — otherwise the parent's "first focusable"
    // (the Avatar button) would steal focus from the child's
    // intentional choice.
    const id = window.requestAnimationFrame(() => {
      if (root.contains(document.activeElement)) return
      const focusable = root.querySelector<HTMLElement>(FOCUSABLE_SELECTOR)
      focusable?.focus()
    })
    return () => window.cancelAnimationFrame(id)
  }, [step])

  // Focus trap + Escape suppression. The gate is non-dismissable, so
  // Esc must not close it; Tab from the last focusable wraps back to
  // the first (and Shift+Tab from the first wraps to the last).
  useEffect(() => {
    if (step === "done") return
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault()
        e.stopPropagation()
        return
      }
      if (e.key !== "Tab") return
      const root = dialogRef.current
      if (!root) return
      const focusables = Array.from(
        root.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR),
      ).filter((el) => el.offsetParent !== null || el === document.activeElement)
      if (focusables.length === 0) return
      const first = focusables[0]
      const last = focusables[focusables.length - 1]
      if (!first || !last) return
      const active = document.activeElement as HTMLElement | null
      if (e.shiftKey && (active === first || !root.contains(active))) {
        e.preventDefault()
        last.focus()
      } else if (!e.shiftKey && active === last) {
        e.preventDefault()
        first.focus()
      }
    }
    document.addEventListener("keydown", handler, true)
    return () => document.removeEventListener("keydown", handler, true)
  }, [step])

  // Drive the shared signal exactly while the flow is visible.
  // The orchestrators (grand tour + per-page useUserTour hooks)
  // subscribe and bail their own work until this flips back to
  // false.
  useEffect(() => {
    const active = step !== "done"
    setFirstRunActive(active)
    return () => {
      // Unmount cleanup — if the flow tears down mid-step (e.g. user
      // signs out), make sure the signal can't be stuck on.
      setFirstRunActive(false)
    }
  }, [step])

  const handlePrivacyAccept = useCallback(() => {
    if (userId) writeFlag(privacyAcceptedKey(userId))
    setStep("setup")
  }, [userId])

  const handleSetupComplete = useCallback(() => {
    if (userId) writeFlag(firstRunSetupKey(userId))
    setStep("picker")
  }, [userId])

  const handleSetupSkip = useCallback(() => {
    // Skip writes the flag too — the user has made the choice to
    // bypass setup; pestering them again next visit is wrong.
    if (userId) writeFlag(firstRunSetupKey(userId))
    setStep("picker")
  }, [userId])

  const closePickerFlow = useCallback(() => {
    if (!userId) return
    writeFlag(firstRunPickerKey(userId))
    // Also tick the grand-tour-seen flag so the cross-page
    // popover tour doesn't auto-fire on top of the user's brand-
    // new enrollment / dashboard. Manual replay via the
    // WelcomeCard "Take a tour" link still works.
    writeFlag(grandTourSeenKey(userId))
  }, [userId])

  const handlePickerEnrolled = useCallback(
    (course: Course) => {
      // Persist the gate-closing flags FIRST so a page refresh
      // mid-splash doesn't loop the user back into the picker. The
      // splash itself is a soft transition — losing it on refresh
      // is fine; losing the enrolled state is not.
      closePickerFlow()
      setEnrolledCourse(course)
      setStep("splash")
    },
    [closePickerFlow],
  )

  const handleSplashComplete = useCallback(() => {
    setStep("done")
    if (enrolledCourse) {
      navigate(`/courses/${enrolledCourse.id}`)
    }
  }, [navigate, enrolledCourse])

  const handlePickerBrowse = useCallback(() => {
    closePickerFlow()
    setStep("done")
  }, [closePickerFlow])

  const handlePickerSkip = useCallback(() => {
    closePickerFlow()
    setStep("done")
  }, [closePickerFlow])

  if (!userId) return null
  if (step === "done") return null

  // Splash has its own fullscreen layout (typographic celebration);
  // skip the modal chrome so it's not constrained by overflow-y-auto
  // + padding. Falls through to ``done`` after ~1.2s via
  // ``handleSplashComplete`` which also fires the navigate.
  if (step === "splash" && enrolledCourse) {
    return (
      <EnrollSplash
        course={enrolledCourse}
        firstName={firstName}
        onComplete={handleSplashComplete}
      />
    )
  }

  // Editorial slide+fade between the three pre-splash steps so the
  // transitions feel like scenes in a play rather than abrupt UI
  // swaps. Cuts to instant for reduced-motion users.
  const motionInitial = prefersReducedMotion
    ? false
    : { opacity: 0, y: 12, scale: 0.985 }
  const motionAnimate = { opacity: 1, y: 0, scale: 1 }
  const motionExit = prefersReducedMotion
    ? { opacity: 0 }
    : { opacity: 0, y: -8, scale: 0.99 }

  return (
    <div
      ref={dialogRef}
      role="dialog"
      aria-modal="true"
      aria-labelledby="first-run-heading"
      className="fixed inset-0 z-[2147483646] flex items-start justify-center overflow-y-auto bg-background/95 px-4 py-10 backdrop-blur-sm sm:items-center sm:py-16"
    >
      <h1 id="first-run-heading" className="sr-only">
        {step === "privacy"
          ? "Privacy policy"
          : step === "setup"
            ? "Quick setup"
            : "Pick your first course"}
      </h1>
      <AnimatePresence mode="wait" initial={false}>
        {step === "privacy" && (
          <motion.div
            key="privacy"
            initial={motionInitial}
            animate={motionAnimate}
            exit={motionExit}
            transition={{ duration: 0.4, ease: EDITORIAL_EASE }}
            className="flex w-full justify-center"
          >
            <PrivacyPolicyStep onAccept={handlePrivacyAccept} />
          </motion.div>
        )}
        {step === "setup" && (
          <motion.div
            key="setup"
            initial={motionInitial}
            animate={motionAnimate}
            exit={motionExit}
            transition={{ duration: 0.4, ease: EDITORIAL_EASE }}
            className="flex w-full justify-center"
          >
            <SetupStep
              firstName={firstName}
              onComplete={handleSetupComplete}
              onSkip={handleSetupSkip}
            />
          </motion.div>
        )}
        {step === "picker" && (
          <motion.div
            key="picker"
            initial={motionInitial}
            animate={motionAnimate}
            exit={motionExit}
            transition={{ duration: 0.4, ease: EDITORIAL_EASE }}
            className="flex w-full justify-center"
          >
            <CoursePickerStep
              firstName={firstName}
              onEnrolled={handlePickerEnrolled}
              onBrowse={handlePickerBrowse}
              onSkip={handlePickerSkip}
            />
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
