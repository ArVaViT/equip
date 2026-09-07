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
// First-run flow finished. The name is the one the flow has used since the
// picker shipped, so a browser that finished the old flow still passes the
// gate — and, from 2026-09, reports that fact to the server.
const PREFIX_FIRST_RUN_COMPLETED = "equip.first-run.completed"
const PREFIX_GRAND_TOUR_SEEN = "equip.grand-tour.seen"
const PREFIX_PER_PAGE_TOUR_SEEN = "equip.tour.seen"
const PREFIX_COMPLETION_CELEBRATED = "equip.celebrated"
const PREFIX_ASSIGNMENT_DRAFT = "equip.draft.assignment"
const PREFIX_BLOCK_DRAFT = "equip.draft.block"

/**
 * Privacy Policy acceptance — a **cache** of what the server holds in
 * ``legal_acceptances``. Trusted only until ``legalService.status()``
 * answers; it stops the gate flashing at somebody who has already agreed,
 * and proves nothing on its own.
 */
export function privacyAcceptedKey(userId: string): string {
  return `${PREFIX_PRIVACY}.${userId}`
}

/**
 * First-run flow finished — a **cache** of ``profiles.onboarding_completed_at``,
 * with the same standing as the privacy flag above. Written when the picker
 * closes; read so the flow does not flash before the profile has loaded; and
 * reported to the server by a browser that holds it while the profile does
 * not, which is how accounts that finished the flow before the server kept a
 * record are healed without anybody being asked again.
 */
export function firstRunCompletedKey(userId: string): string {
  return `${PREFIX_FIRST_RUN_COMPLETED}.${userId}`
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

/**
 * An unsent assignment draft — per ``(userId, assignmentId)``.
 *
 * User-scoped like the rest, and that matters more here than anywhere else in
 * this file: these devices are shared. A brother opening the laptop after his
 * sister must not find her half-written essay in his textarea.
 */
export function assignmentDraftKey(userId: string, assignmentId: string): string {
  return `${PREFIX_ASSIGNMENT_DRAFT}.${userId}.${assignmentId}`
}

/**
 * A teacher's text block as last typed in this browser — per
 * ``(userId, blockId)``.
 *
 * Written while the block is being edited and removed once the server has
 * the same text. What remains in storage after a crash, an expired session
 * or a closed tab is therefore exactly the text the server never received.
 */
export function blockDraftKey(userId: string, blockId: string): string {
  return `${PREFIX_BLOCK_DRAFT}.${userId}.${blockId}`
}
