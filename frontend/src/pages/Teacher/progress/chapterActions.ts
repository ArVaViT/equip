import { isGradableChapterType } from "@/lib/chapterTypes"
import type { StudentChapterInfo } from "@/types"

/** Which of the three controls a chapter row should offer. */
export interface ChapterActions {
  /** Waive the work: it stops counting toward the grade and the chapter closes. */
  canExcuse: boolean
  /** Undo a waiver. Replaces the completion toggle, never sits beside it. */
  canReturn: boolean
  /** The ordinary "mark complete / undo" pair. */
  canToggleCompletion: boolean
}

/**
 * An excused chapter offers exactly one action, and it is not the completion
 * toggle.
 *
 * The exemption holds two things together — the item is out of the grade *and*
 * its chapter counts as done — and the server refuses to break that pair
 * (409 on the incomplete route). Showing "Undo" there would be a button whose
 * only possible outcome is an error toast. "Return the work" undoes both
 * halves, which is what the teacher meant anyway.
 *
 * Excusing stays available on a chapter the student already finished: someone
 * who submitted while ill can still be waived from the mark, and the completion
 * they earned is left exactly as it is.
 */
export function chapterActions(chapter: StudentChapterInfo | undefined): ChapterActions {
  const none = { canExcuse: false, canReturn: false, canToggleCompletion: false }
  if (!chapter || !isGradableChapterType(chapter.chapter_type)) return none

  const excused = chapter.completed_by === "excused"
  return {
    // Only work that exists can be waived — a gradable chapter with neither a
    // quiz nor an assignment behind it has nothing to excuse anyone from.
    canExcuse: !excused && chapter.gradable_item !== null,
    canReturn: excused,
    canToggleCompletion: !excused,
  }
}
