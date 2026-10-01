import { isGradableChapterType } from "@/lib/chapterTypes"
import { readCourseStructure } from "@/lib/courseStructure"
import { isChapterLocked } from "@/pages/Course/moduleProgress"
import type { Chapter, Course, Enrollment } from "@/types"

/**
 * Which course the "Continue" card offers: the most recently opened one
 * that is not finished; else — on a new device, where the recently opened
 * list is empty — one already started, most recently joined first; else
 * the most recently joined unfinished one. Without the middle step a
 * student halfway through one course was sent to the untouched course
 * they had joined last.
 *
 * "Not finished" reads both halves of progress, as the dashboard does:
 * `progress` counts only assessed work, so a course of readings sits at 0%
 * however far somebody has read.
 */
export function courseToContinue(enrollments: Enrollment[], recentIds: string[]): Enrollment | null {
  const open = enrollments.filter(
    (e) => e.course && (e.progress < 100 || e.chapters_read < e.chapters_to_read),
  )
  if (open.length === 0) return null
  for (const id of recentIds) {
    const hit = open.find((e) => e.course_id === id)
    if (hit) return hit
  }
  const started = (e: Enrollment) => e.progress > 0 || e.chapters_read > 0
  return (
    [...open].sort(
      (a, b) => Number(started(b)) - Number(started(a)) || b.enrolled_at.localeCompare(a.enrolled_at),
    )[0] ?? null
  )
}

/**
 * The first lesson in reading order not yet done and not locked, with its
 * place in the course. A lesson behind a lock (a test still to be graded, a
 * teacher's "not ready") is not somewhere to send a person; `null` when every
 * lesson left is locked or done.
 */
export function nextLesson(
  course: Course,
  done: readonly string[],
): { chapter: Chapter; position: number; total: number } | null {
  const chapters = readCourseStructure(course).chapters
  const finished = new Set(done)
  for (let i = 0; i < chapters.length; i++) {
    const chapter = chapters[i]!
    if (finished.has(chapter.id)) continue
    const previous = i > 0 ? chapters[i - 1]! : null
    const locked = isChapterLocked(
      finished,
      chapter,
      previous,
      previous ? isGradableChapterType(previous.chapter_type) : false,
    )
    if (!locked) return { chapter, position: i + 1, total: chapters.length }
  }
  return null
}
