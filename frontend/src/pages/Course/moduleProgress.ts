/**
 * What the module page may claim about a student's progress.
 *
 * This lived inline in the JSX, which is how it went wrong. `getMyChapterProgress`
 * answered `[]` when the request failed, so "we could not find out" and "you
 * have finished nothing" were the same value — and two different consequences
 * followed from it:
 *
 * - every chapter drew as incomplete, so a student who had finished the module
 *   met a page of empty circles and a count of zero;
 * - and worse, `!completed.has(previous)` was `true`, so every gated chapter
 *   drew as **locked**. A timed-out request walled somebody out of chapters
 *   they had already earned.
 *
 * Hence `completed: Set | null`, and hence the asymmetry below: unknown
 * progress never marks a chapter complete, and never locks one either. The
 * server is the real gate — a client guess can only be wrong in one of two
 * directions, and wrongly denying somebody their own progress is the worse one.
 */
export interface ChapterLike {
  id: string
  is_locked?: boolean
}

/** `null` means the progress request failed. It is not an empty set. */
export type CompletedIds = Set<string> | null

export function isChapterComplete(
  completed: CompletedIds,
  chapter: ChapterLike,
  isGradable: boolean,
): boolean {
  if (completed === null) return false
  return isGradable && completed.has(chapter.id)
}

/**
 * Why a chapter is shut, when it is.
 *
 * Two different locks wore the same flag and only one of them worked.
 *
 * `"sequence"` is the one that did: finish the assessment before this
 * lesson and it opens. The reader is told how, because there is a how.
 *
 * `"teacher"` is the one that did not. A locked lesson whose
 * predecessor is a reading — or that has no predecessor — has nothing
 * a reader could complete, and the old rule read that as "not locked".
 * So three unwritten lessons of a live course stood open to everybody
 * the day it launched. Nothing to earn means the teacher shut it, and
 * a teacher's lock does not open by reading harder.
 */
export type LockReason = "sequence" | "teacher"

export function chapterLockReason(
  completed: CompletedIds,
  chapter: ChapterLike,
  previous: ChapterLike | null,
  previousIsGradable: boolean,
): LockReason | null {
  if (!chapter.is_locked) return null
  if (previous === null || !previousIsGradable) return "teacher"
  // Fails open on unknown progress, and only here: this is the lock a
  // reader can open, so guessing wrong would wall them out of what
  // they have already earned. See the note at the top.
  if (completed === null) return null
  return completed.has(previous.id) ? null : "sequence"
}

export function isChapterLocked(
  completed: CompletedIds,
  chapter: ChapterLike,
  previous: ChapterLike | null,
  previousIsGradable: boolean,
): boolean {
  return chapterLockReason(completed, chapter, previous, previousIsGradable) !== null
}

/**
 * Whether a whole module is gated behind an unfinished predecessor.
 *
 * The same `[]`-on-failure fallback lived here too, and this was the worst of
 * the three places: a failed request walled a student out of everything after
 * the module they had actually completed, not merely one chapter.
 */
export function isModuleLocked(completed: CompletedIds, previousGradableIds: string[]): boolean {
  if (completed === null) return false
  if (previousGradableIds.length === 0) return false
  return !previousGradableIds.every((id) => completed.has(id))
}

/**
 * A reading chapter the student has marked as read.
 *
 * Deliberately separate from `isChapterComplete`, and rendered differently: a
 * lesson you have read is not an assessment you have passed, and one tick for
 * both would blur the only distinction the progress percentage rests on.
 *
 * It exists because the read control shipped without it. A student could mark
 * a chapter read, the server stored it, `getMyChapterProgress` returned it —
 * and every list dropped it on the floor, because the row only drew state for
 * gradable chapters. The button appeared to do nothing.
 */
export function isChapterRead(
  completed: CompletedIds,
  chapter: ChapterLike,
  isGradable: boolean,
): boolean {
  if (completed === null) return false
  return !isGradable && completed.has(chapter.id)
}
