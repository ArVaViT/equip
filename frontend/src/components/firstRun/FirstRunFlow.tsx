import { useCallback, useEffect, useRef, useState } from "react"
import { useAuth } from "@/context/useAuth"
import { setFirstRunActive } from "@/lib/tourState"
import { PrivacyPolicyStep } from "./PrivacyPolicyStep"
import { SetupStep } from "./SetupStep"

/** CSS selector for elements eligible for the focus trap. Mirrors
 *  the WAI-ARIA "tabbable elements" definition without depending on
 *  a focus-trap library — same shape used by Radix UI internally. */
const FOCUSABLE_SELECTOR =
  'a[href], button:not([disabled]), input:not([disabled]):not([type="hidden"]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'

const STORAGE_PREFIX_PRIVACY = "equip.privacy.accepted"
const STORAGE_PREFIX_SETUP = "equip.first-run.completed"

function privacyKey(userId: string): string {
  return `${STORAGE_PREFIX_PRIVACY}.${userId}`
}

function setupKey(userId: string): string {
  return `${STORAGE_PREFIX_SETUP}.${userId}`
}

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

type Step = "privacy" | "setup" | "done"

function decideInitialStep(userId: string | undefined): Step {
  if (!userId) return "done"
  if (!readFlag(privacyKey(userId))) return "privacy"
  if (!readFlag(setupKey(userId))) return "setup"
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
  const userId = user?.id
  const dialogRef = useRef<HTMLDivElement>(null)
  // ``useState`` initialiser runs once per mount; ``userId`` change
  // (sign-in, account switch) re-derives via the effect below.
  const [step, setStep] = useState<Step>(() => decideInitialStep(userId))

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
    if (userId) writeFlag(privacyKey(userId))
    setStep("setup")
  }, [userId])

  const handleSetupComplete = useCallback(() => {
    if (userId) writeFlag(setupKey(userId))
    setStep("done")
  }, [userId])

  const handleSetupSkip = useCallback(() => {
    // Skip writes the flag too — the user has made the choice to
    // bypass setup; pestering them again next visit is wrong.
    if (userId) writeFlag(setupKey(userId))
    setStep("done")
  }, [userId])

  if (!userId) return null
  if (step === "done") return null

  return (
    <div
      ref={dialogRef}
      role="dialog"
      aria-modal="true"
      aria-labelledby="first-run-heading"
      className="fixed inset-0 z-[2147483646] flex items-start justify-center overflow-y-auto bg-background/95 px-4 py-10 backdrop-blur-sm sm:items-center sm:py-16"
    >
      <h1 id="first-run-heading" className="sr-only">
        {step === "privacy" ? "Privacy policy" : "Quick setup"}
      </h1>
      {step === "privacy" && <PrivacyPolicyStep onAccept={handlePrivacyAccept} />}
      {step === "setup" && (
        <SetupStep onComplete={handleSetupComplete} onSkip={handleSetupSkip} />
      )}
    </div>
  )
}
