/**
 * Single source of truth for every ``localStorage`` key used by the
 * onboarding + tour stack. Centralising the prefixes here removes
 * two real risks the audit caught:
 *
 *   1. Two modules independently writing the same logical flag with
 *      string literals — ``equip.grand-tour.seen`` was hard-coded
 *      in both ``FirstRunFlow.tsx`` and ``useGrandTour.ts``. A typo
 *      in one place would silently desync the tour suppression.
 *
 *   2. The "suppress per-page tours that the grand tour covered"
 *      helper inside ``useGrandTour`` knew the EXACT key format
 *      used by ``useUserTour`` — string-formatted across modules,
 *      undocumented coupling. Now both go through the same
 *      ``perPageTourSeenKey`` builder.
 *
 * Every key follows the ``equip.<domain>.<aspect>`` shape with
 * dot separators (no colons — except the legacy locale key, which
 * the i18n bundle still reads at boot time and we don't want to
 * migrate in flight). User-scoped keys append ``.<userId>`` so a
 * shared device's second account starts with a clean slate.
 */

const PREFIX_PRIVACY = "equip.privacy.accepted"
const PREFIX_FIRST_RUN_SETUP = "equip.first-run.setup"
// Picker completion (== "first-run flow closed"). Reuses the legacy
// "equip.first-run.completed" name so users who cleared the
// pre-picker flow on prod don't see the picker pop up on next visit.
const PREFIX_FIRST_RUN_PICKER = "equip.first-run.completed"
const PREFIX_GRAND_TOUR_SEEN = "equip.grand-tour.seen"
const PREFIX_PER_PAGE_TOUR_SEEN = "equip.tour.seen"
const PREFIX_COMPLETION_CELEBRATED = "equip.celebrated"

/** Privacy Policy acceptance flag — gates step 1 of the first-run flow. */
export function privacyAcceptedKey(userId: string): string {
  return `${PREFIX_PRIVACY}.${userId}`
}

/** Quick-Setup completion flag — gates step 2 (avatar / name / theme / locale). */
export function firstRunSetupKey(userId: string): string {
  return `${PREFIX_FIRST_RUN_SETUP}.${userId}`
}

/**
 * Picker / first-run-overall completion flag — gates step 3 AND
 * closes the gate. Once this is set, the modal stays closed
 * regardless of the other two flags' state.
 */
export function firstRunPickerKey(userId: string): string {
  return `${PREFIX_FIRST_RUN_PICKER}.${userId}`
}

/**
 * Grand-tour seen flag — set by the cross-page tour itself when it
 * completes/dismisses, AND by ``FirstRunFlow`` when the picker
 * closes (so the cross-page tour doesn't auto-fire on top of a
 * just-enrolled student).
 */
export function grandTourSeenKey(userId: string): string {
  return `${PREFIX_GRAND_TOUR_SEEN}.${userId}`
}

/**
 * Per-page tour seen flag — one per ``(userId, tourId)``. Written
 * by ``useUserTour`` when the user dismisses or completes a
 * single-page tour, AND by the grand tour's ``onDone``/``onSkipped``
 * for every tour id in ``STUDENT_GRAND_TOUR_COVERS`` so revisits of
 * those surfaces don't get a second wave of contextual tours.
 */
export function perPageTourSeenKey(userId: string, tourId: string): string {
  return `${PREFIX_PER_PAGE_TOUR_SEEN}.${userId}.${tourId}`
}

/**
 * Course-completion celebration flag — per ``(userId, courseId)``.
 * Written by ``EnrolledView`` when the student closes the
 * ``CompletionDialog`` for a course that just hit 100% progress,
 * so the celebration doesn't re-fire on every revisit.
 */
export function completionCelebratedKey(userId: string, courseId: string): string {
  return `${PREFIX_COMPLETION_CELEBRATED}.${userId}.${courseId}`
}
