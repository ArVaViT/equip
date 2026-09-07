import { useCallback, useEffect, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { AnimatePresence, motion, useReducedMotion } from "motion/react"
import { useLocation, useNavigate } from "react-router-dom"
import { legalService } from "@/services/legal"
import { onboardingService } from "@/services/onboarding"
import { useAuth } from "@/context/useAuth"
import { setFirstRunActive } from "@/lib/tourState"
import type { Course } from "@/types"
import { PrivacyPolicyStep } from "./PrivacyPolicyStep"
import { NameStep } from "./NameStep"
import { CoursePickerStep } from "./CoursePickerStep"
import { EnrollSplash } from "./EnrollSplash"
import { firstNameOf } from "@/lib/names"
import { EDITORIAL_EASE } from "@/lib/motion"
import { firstRunCompletedKey, privacyAcceptedKey, grandTourSeenKey } from "@/lib/storageKeys"
import { clearFlag, decideInitialStep, readFlag, writeFlag, type Step } from "./firstRunStep"

/** CSS selector for elements eligible for the focus trap. Mirrors
 *  the WAI-ARIA "tabbable elements" definition without depending on
 *  a focus-trap library — same shape used by Radix UI internally. */
const FOCUSABLE_SELECTOR =
  'a[href], button:not([disabled]), input:not([disabled]):not([type="hidden"]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'

/**
 * Full-screen first-run orchestrator: consent → (name) → course picker →
 * done. Which step applies is decided in ``firstRunStep.ts``, from the
 * server's answers: `legalService.status()` for consent and
 * `profiles.onboarding_completed_at` for the rest. The two `localStorage`
 * flags are caches of those answers, so nothing flashes before they arrive.
 *
 * Rendered above everything else (z-index above the grand tour overlay's
 * 1000000000) so it blocks all interaction until the person is through, or
 * closes the browser.
 *
 * Signals to the ``tourState`` module while it's mounted so the grand tour
 * and every per-page tour bail their own auto-starts. They resume the
 * moment this component unmounts.
 *
 * Mount once inside ``AppRoutes`` (after AuthProvider) — see ``App.tsx``.
 * Mounting in multiple places will race the modal stack.
 */
export function FirstRunFlow() {
  const { user, applyUser } = useAuth()
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { pathname } = useLocation()
  const prefersReducedMotion = useReducedMotion()
  // Primitives rather than the ``user`` object: a Supabase TOKEN_REFRESHED
  // rewrites the object without changing any of these, and the effects
  // below must not re-derive the step over nothing.
  const userId = user?.id
  const role = user?.role
  const fullName = user?.full_name ?? null
  const completedAt = user?.onboarding_completed_at ?? null
  const firstName = firstNameOf(user?.full_name)
  const dialogRef = useRef<HTMLDivElement>(null)

  /**
   * The two routes the gate itself points at.
   *
   * Found on production within minutes of shipping: this component mounts on
   * every route, so clicking «Политика конфиденциальности» from the gate
   * opened the document in a new tab — where the gate mounted again and
   * covered it. Different mechanism from the original bug, identical outcome:
   * the platform asking somebody to accept a text they cannot read.
   *
   * A gate that blocks its own escape hatch is not a gate, it is a wall.
   */
  const exempt = pathname === "/privacy" || pathname === "/terms"

  // null until the server has answered. See `decideInitialStep`.
  const [legalOutstanding, setLegalOutstanding] = useState<boolean | null>(null)
  // Whether this person has accepted *some* version before. When they have
  // and something is outstanding anyway, the documents changed under them —
  // and the screen must say so rather than greet them as a newcomer.
  const [acceptedBefore, setAcceptedBefore] = useState(false)
  // Skipped the name step this session. Without this, the legal answer
  // landing a moment after the skip would re-derive the step and send the
  // person back to the question they had just declined.
  const nameDeclined = useRef(false)
  // The completion report already sent (or in flight) for this user, so the
  // picker closing and the cache-heal effect below cannot both post it.
  const reportedFor = useRef<string | null>(null)
  const [step, setStep] = useState<Step>(() => (exempt ? "done" : decideInitialStep(user, null)))
  // The course the user enrolled in via the picker. Drives the
  // EnrollSplash celebration and the post-splash navigation. We
  // keep it as state (not a ref) so the splash re-renders on
  // ``setStep("splash")`` with the freshest value.
  const [enrolledCourse, setEnrolledCourse] = useState<Course | null>(null)

  useEffect(() => {
    if (!userId) {
      setLegalOutstanding(null)
      setAcceptedBefore(false)
      return
    }
    let cancelled = false
    legalService
      .status()
      .then((status) => {
        if (cancelled) return
        const owed = status.outstanding.length > 0
        setLegalOutstanding(owed)
        setAcceptedBefore(status.accepted.length > 0)
        // Keep the cache honest in both directions, including the case that
        // matters: somebody who accepted on their phone should not meet the
        // gate again on the laptop just because this browser never saw it.
        if (owed) clearFlag(privacyAcceptedKey(userId))
        else writeFlag(privacyAcceptedKey(userId))
      })
      .catch(() => {
        // A failed check must not become a gate nobody can pass, and must not
        // become a silent pass either. Staying at `null` leaves the product
        // usable and asks again on the next load — the same behaviour as
        // somebody who closed the browser mid-gate.
        if (!cancelled) setLegalOutstanding(null)
      })
    return () => {
      cancelled = true
    }
  }, [userId])

  // Re-derive the step whenever a fact it depends on changes. The splash is
  // the one step that must survive this: the completion report lands while
  // it plays, and "done" here would cut it short and lose the navigation
  // into the course.
  useEffect(() => {
    const next = exempt
      ? "done"
      : decideInitialStep(
          userId && role
            ? { id: userId, role, full_name: fullName, onboarding_completed_at: completedAt }
            : null,
          legalOutstanding,
          nameDeclined.current,
        )
    setStep((prev) => (prev === "splash" ? prev : next))
  }, [userId, role, fullName, completedAt, legalOutstanding, exempt])

  const reportCompletion = useCallback(() => {
    if (!userId || reportedFor.current === userId) return
    reportedFor.current = userId
    onboardingService.complete().then(applyUser, () => {
      // The cache still closes the gate in this browser; the next visit
      // reports again. Nothing to tell the person.
      reportedFor.current = null
    })
  }, [userId, applyUser])

  // The server has no record that this person finished the flow, but the
  // flow is not going to show them anything: either this browser holds the
  // old flag (they finished before the server kept a record), or they are
  // not a student and never had a picker to finish. Tell the server, so the
  // next device does not depend on this one. Waits for consent to settle —
  // the mark means "through the flow", and consent is the flow's first step.
  useEffect(() => {
    if (!userId || !role || completedAt || legalOutstanding !== false) return
    const finished = readFlag(firstRunCompletedKey(userId)) || role !== "student"
    if (finished) reportCompletion()
  }, [userId, role, completedAt, legalOutstanding, reportCompletion])

  // Autofocus the first focusable element on each step transition so
  // keyboard users land inside the dialog. Otherwise focus stays on
  // ``<body>`` and Tab walks into the hidden page underneath.
  useEffect(() => {
    if (step === "done") return
    const root = dialogRef.current
    if (!root) return
    // ``requestAnimationFrame`` instead of immediate query so React's
    // commit has settled and the focusable elements actually exist.
    // We yield to a step-specific autofocus (``NameStep`` focuses its
    // input) by skipping if focus is already inside the dialog.
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
    // The step effect takes it from here: name, picker, or — for somebody
    // re-accepting changed documents — straight back into the product.
    setLegalOutstanding(false)
  }, [userId])

  const handleNameDone = useCallback(() => {
    nameDeclined.current = true
    setStep("picker")
  }, [])

  const closePickerFlow = useCallback(() => {
    if (!userId) return
    writeFlag(firstRunCompletedKey(userId))
    // Also tick the grand-tour-seen flag so the cross-page
    // popover tour doesn't auto-fire on top of the user's brand-
    // new enrollment / dashboard. Manual replay via the
    // WelcomeCard "Take a tour" link still works.
    writeFlag(grandTourSeenKey(userId))
    reportCompletion()
  }, [userId, reportCompletion])

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

  // Editorial slide+fade between the pre-splash steps so the
  // transitions feel like scenes in a play rather than abrupt UI
  // swaps. Cuts to instant for reduced-motion users.
  const motionInitial = prefersReducedMotion
    ? false
    : { opacity: 0, y: 12, scale: 0.985 }
  const motionAnimate = { opacity: 1, y: 0, scale: 1 }
  const motionExit = prefersReducedMotion
    ? { opacity: 0 }
    : { opacity: 0, y: -8, scale: 0.99 }

  const heading =
    step === "privacy"
      ? t(acceptedBefore ? "firstRun.privacy.renewal.eyebrow" : "firstRun.privacy.eyebrow")
      : step === "name"
        ? t("firstRun.name.eyebrow")
        : t("firstRun.picker.eyebrow")

  return (
    <div
      ref={dialogRef}
      role="dialog"
      aria-modal="true"
      aria-labelledby="first-run-heading"
      className="fixed inset-0 z-[2147483646] flex items-start justify-center overflow-y-auto bg-surface px-4 py-10 sm:items-center sm:py-16"
    >
      {/* The name a screen reader announces for this dialog. It was written
          in English at the call site, so every reader who is not reading in
          English had the one part of the first-run flow they cannot see
          announced in a language they did not choose. */}
      <h1 id="first-run-heading" className="sr-only">
        {heading}
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
            <PrivacyPolicyStep onAccept={handlePrivacyAccept} renewal={acceptedBefore} />
          </motion.div>
        )}
        {step === "name" && (
          <motion.div
            key="name"
            initial={motionInitial}
            animate={motionAnimate}
            exit={motionExit}
            transition={{ duration: 0.4, ease: EDITORIAL_EASE }}
            className="flex w-full justify-center"
          >
            <NameStep onDone={handleNameDone} />
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
              onSkip={handlePickerSkip}
            />
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
