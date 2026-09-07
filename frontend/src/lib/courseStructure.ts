import type { Chapter, Course, Module } from "@/types"

/**
 * One reading of a course's shape, for every screen that needs it.
 *
 * A chapter belongs to a course; a module is an optional grouping over
 * chapters of that course. So the course payload arrives in two halves —
 * `modules[].chapters` for the grouped ones, `chapters` for the rest — and
 * the server guarantees the halves are a partition: every live chapter is in
 * exactly one of them.
 *
 * Every screen used to re-derive that shape for itself: sort the modules,
 * sort the chapters inside each, walk the pair of loops, and (for "what
 * comes next") walk them again a level at a time. That two-level walk is
 * what made "the next lesson" stop at a module boundary, and it has no
 * answer at all for a lesson that is in no module. Reading the course once,
 * here, gives both things a screen actually wants: the outline to render and
 * the flat order to navigate.
 *
 * Order of reading — the same rule the server and the teacher's report use:
 *   1. modules by `order_index`, and
 *   2. chapters inside a module by their own `order_index`,
 *   3. then the chapters that are in no module, as one group at the tail.
 */

/**
 * The id the teacher's reports give the stand-in group holding the lessons
 * that are in no module.
 *
 * The reports (progress board, gradebook) group by a non-null id so a screen
 * can group by one key without a special case, and the server mints this one
 * for the loose lessons. It is not a module id and no module has it — it is
 * a sentinel, and mirrors `UNGROUPED_GROUP_ID` in
 * `backend/app/services/course_structure.py`. The course tree itself does
 * not use it: there `module_id` is simply `null`.
 */
export const UNGROUPED_GROUP_ID = "__ungrouped__"

/** A heading in the outline: a module, or the tail of ungrouped lessons. */
export interface CourseOutlineGroup {
  /** The module's id, or `null` for the ungrouped tail. */
  moduleId: string | null
  /** The module itself, or `null` for the ungrouped tail — so a caller can
   *  reach for `title` / `due_date` without a second lookup. */
  module: Module | null
  /** This group's lessons, in reading order. */
  chapters: Chapter[]
}

export interface CourseStructure {
  /** The outline: modules in order, then the ungrouped tail if it has anything
   *  in it. A module with no lessons keeps its place — an empty module is a
   *  thing a teacher can see and fill, not a thing to hide. */
  groups: CourseOutlineGroup[]
  /** Every lesson of the course, flat, in reading order. This is the order
   *  "previous" and "next" walk. */
  chapters: Chapter[]
}

const EMPTY: CourseStructure = { groups: [], chapters: [] }

function byOrderIndex<T extends { order_index: number }>(a: T, b: T): number {
  return a.order_index - b.order_index
}

/** Soft-deleted rows are dropped wherever a payload still carries them: a
 *  deleted lesson must not take up a place in the outline, and must never be
 *  the answer to "what comes next". */
function isLive(row: { deleted_at?: string | null } | null | undefined): boolean {
  return Boolean(row) && !row!.deleted_at
}

/**
 * Read a course payload into an outline and a flat reading order.
 *
 * Tolerant of a partial course on purpose: `modules` and `chapters` are both
 * optional on the wire (a course list omits them), and a screen holding
 * `null` while it loads should get an empty structure rather than a branch.
 */
export function readCourseStructure(course: Course | null | undefined): CourseStructure {
  if (!course) return EMPTY

  const groups: CourseOutlineGroup[] = []
  const flat: Chapter[] = []
  // The server promises the two halves do not overlap. Trusting that promise
  // and also checking it costs one Set and removes a whole class of bug from
  // a stale cache holding a pre-migration payload, where a lesson appeared
  // both inside its module and at the root.
  const seen = new Set<string>()

  const push = (chapter: Chapter, into: Chapter[]): void => {
    if (!isLive(chapter) || seen.has(chapter.id)) return
    seen.add(chapter.id)
    into.push(chapter)
    flat.push(chapter)
  }

  const modules = (course.modules ?? []).filter(isLive).sort(byOrderIndex)
  for (const module of modules) {
    const chapters: Chapter[] = []
    for (const chapter of [...(module.chapters ?? [])].sort(byOrderIndex)) {
      push(chapter, chapters)
    }
    groups.push({ moduleId: module.id, module, chapters })
  }

  const ungrouped: Chapter[] = []
  for (const chapter of [...(course.chapters ?? [])].sort(byOrderIndex)) {
    push(chapter, ungrouped)
  }
  // No empty tail: a course whose every lesson sits in a module should not
  // grow a nameless heading with nothing under it.
  if (ungrouped.length > 0) {
    groups.push({ moduleId: null, module: null, chapters: ungrouped })
  }

  return { groups, chapters: flat }
}

/**
 * How many lessons the course has, preferring the count the server computed.
 *
 * `chapter_count` is a query, not a `length` — it is right even on a course
 * summary that carries no `modules` at all, which is exactly where a catalog
 * card needs it. The walk is the fallback for a payload from before the
 * counts existed.
 */
export function countChapters(course: Course | null | undefined): number {
  if (!course) return 0
  if (typeof course.chapter_count === "number") return course.chapter_count
  return readCourseStructure(course).chapters.length
}

/** As `countChapters`, for modules. */
export function countModules(course: Course | null | undefined): number {
  if (!course) return 0
  if (typeof course.module_count === "number") return course.module_count
  return (course.modules ?? []).filter(isLive).length
}

/** Where the lesson sits in the reading order, and which group holds it. */
export interface ChapterPlacement {
  chapter: Chapter
  /** Index in `CourseStructure.chapters`. */
  index: number
  /** The group the lesson is in — `moduleId: null` for an ungrouped one. */
  group: CourseOutlineGroup
  /** The lesson before it in the course, across group boundaries. */
  prev: Chapter | null
  /** The lesson after it in the course, across group boundaries. The point of
   *  the flat order: the last lesson of a module leads into the first of the
   *  next one rather than into a dead end. */
  next: Chapter | null
}

/** Find a lesson in the course and say what is around it. `null` when the
 *  course does not hold it — a stale link, or a lesson since deleted. */
export function findChapter(
  structure: CourseStructure,
  chapterId: string | null | undefined,
): ChapterPlacement | null {
  if (!chapterId) return null
  const index = structure.chapters.findIndex((c) => c.id === chapterId)
  if (index === -1) return null
  const group = structure.groups.find((g) => g.chapters.some((c) => c.id === chapterId))!
  return {
    chapter: structure.chapters[index]!,
    index,
    group,
    prev: structure.chapters[index - 1] ?? null,
    next: structure.chapters[index + 1] ?? null,
  }
}

/**
 * The address of a lesson. Course-shaped, always — it is the one address
 * every lesson has, and it does not go stale when a teacher regroups the
 * course. The module-shaped address still resolves, so links already sent
 * out keep working; nothing needs to mint a new one.
 */
export function chapterHref(courseId: string, chapterId: string): string {
  return `/courses/${courseId}/chapters/${chapterId}`
}

/** The teacher's address for editing a lesson. Course-shaped, as above. */
export function chapterEditHref(courseId: string, chapterId: string): string {
  return `/teacher/courses/${courseId}/chapters/${chapterId}/edit`
}
