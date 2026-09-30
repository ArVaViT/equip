import { readCourseStructure } from "@/lib/courseStructure"
import type { Chapter, Course, Enrollment } from "@/types"

/**
 * Which course the "Continue" card offers: the most recently opened one
 * that is not finished, else the most recently joined unfinished one.
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
  return [...open].sort((a, b) => b.enrolled_at.localeCompare(a.enrolled_at))[0] ?? null
}

/** The first lesson in reading order not yet done, with its place in the course. */
export function nextLesson(
  course: Course,
  done: readonly string[],
): { chapter: Chapter; position: number; total: number } | null {
  const chapters = readCourseStructure(course).chapters
  const finished = new Set(done)
  const index = chapters.findIndex((c) => !finished.has(c.id))
  if (index < 0) return null
  return { chapter: chapters[index]!, position: index + 1, total: chapters.length }
}
