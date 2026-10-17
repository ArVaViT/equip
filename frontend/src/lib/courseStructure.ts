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
 * Order of reading — one order for everybody, the one the teacher set; the
 * same rule as `build_spine` in `backend/app/services/course_structure.py`:
 *   1. a module and a lesson in no module each take a place in one sequence,
 *      numbered in one shared space by their own `order_index` (ties: the
 *      module first, then by id);
 *   2. a module's lessons run under it by their own `order_index`, which is
 *      never compared with anything outside the module.
 * So a lesson the teacher put between two modules is read there — by the
 * student, by "next lesson", and in the teacher's own editor.
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

/** A stretch of the outline: a module with its lessons, or consecutive
 *  lessons that sit in no module. */
export interface CourseOutlineGroup {
  /** The module's id, or `null` for a stretch of ungrouped lessons. */
  moduleId: string | null
  /** The module itself, or `null` for ungrouped lessons — so a caller can
   *  reach for `title` / `due_date` without a second lookup. */
  module: Module | null
  /** This group's lessons, in reading order. */
  chapters: Chapter[]
}

export interface CourseStructure {
  /** The outline in reading order. Ungrouped lessons appear where they were
   *  put, as stretches between modules — so more than one group can have
   *  `moduleId: null`. A module with no lessons keeps its place — an empty
   *  module is a thing a teacher can see and fill, not a thing to hide. */
  groups: CourseOutlineGroup[]
  /** Every lesson of the course, flat, in reading order. This is the order
   *  "previous" and "next" walk. */
  chapters: Chapter[]
}

const EMPTY: CourseStructure = { groups: [], chapters: [] }

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

  type Place = { order: number; kind: 0 | 1; id: string; module?: Module; chapter?: Chapter }
  const places: Place[] = []
  for (const module of (course.modules ?? []).filter(isLive)) {
    places.push({ order: module.order_index, kind: 0, id: module.id, module })
  }
  for (const chapter of course.chapters ?? []) {
    places.push({ order: chapter.order_index, kind: 1, id: chapter.id, chapter })
  }
  places.sort((a, b) => a.order - b.order || a.kind - b.kind || compareIds(a.id, b.id))

  // Grouped lessons first into the `seen` set, so a stale payload holding a
  // lesson both in its module and at the root shows it in its module.
  const moduleLessons = new Map<string, Chapter[]>()
  for (const place of places) {
    if (!place.module) continue
    const chapters = [...(place.module.chapters ?? [])].sort(
      (a, b) => a.order_index - b.order_index || compareIds(a.id, b.id),
    )
    moduleLessons.set(place.module.id, chapters)
  }
  const grouped = new Set([...moduleLessons.values()].flat().filter(isLive).map((c) => c.id))

  let loose: CourseOutlineGroup | null = null
  for (const place of places) {
    if (place.module) {
      loose = null
      const chapters: Chapter[] = []
      for (const chapter of moduleLessons.get(place.module.id) ?? []) push(chapter, chapters)
      groups.push({ moduleId: place.module.id, module: place.module, chapters })
      continue
    }
    const chapter = place.chapter!
    if (grouped.has(chapter.id)) continue
    if (!loose) {
      loose = { moduleId: null, module: null, chapters: [] }
      groups.push(loose)
    }
    push(chapter, loose.chapters)
  }

  // No empty stretch: a soft-deleted loose lesson must not leave a nameless
  // group with nothing in it.
  return { groups: groups.filter((g) => g.module !== null || g.chapters.length > 0), chapters: flat }
}

/** Code-point order, as Python compares strings — the server breaks ties
 *  the same way, so both read one order. */
function compareIds(a: string, b: string): number {
  return a < b ? -1 : a > b ? 1 : 0
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

/**
 * New `order_index` values for a list of lessons the teacher has just
 * reordered inside one module: the numbers the lessons already had, handed
 * out again in the new order. Inside a module a number only orders that
 * module's lessons, so any distinct ascending numbers would do; reusing the
 * same ones keeps the request count down to the rows that moved. Ties are
 * pulled apart so the new order is the only one the numbers can mean.
 */
export function reuseOrderNumbers<T extends { order_index: number }>(before: T[], after: T[]): T[] {
  const numbers = before.map((c) => c.order_index).sort((a, b) => a - b)
  let last = -Infinity
  return after.map((c, i) => {
    const n = Math.max(numbers[i] ?? i, last + 1)
    last = n
    return { ...c, order_index: n }
  })
}

/**
 * The course as the teacher's editor arranges it: one list of places, each a
 * module (with its lessons) or a single lesson that sits in no module. This
 * is the list the editor drags, and the shape `PUT /courses/{id}/outline`
 * takes.
 */
export type OutlinePlace =
  | { kind: "module"; module: Module; chapters: Chapter[] }
  | { kind: "lesson"; chapter: Chapter }

/** The places of a course, in reading order. */
export function outlinePlaces(structure: CourseStructure): OutlinePlace[] {
  const places: OutlinePlace[] = []
  for (const group of structure.groups) {
    if (group.module) places.push({ kind: "module", module: group.module, chapters: group.chapters })
    else for (const chapter of group.chapters) places.push({ kind: "lesson", chapter })
  }
  return places
}

/** Move one place — a module with its lessons, or a loose lesson. */
export function movePlace(places: OutlinePlace[], from: number, to: number): OutlinePlace[] {
  const next = [...places]
  const [moved] = next.splice(from, 1)
  if (!moved) return places
  next.splice(to, 0, moved)
  return next
}

/** Reorder the lessons inside one module. Nothing outside it moves. */
export function moveInModule(places: OutlinePlace[], moduleId: string, from: number, to: number): OutlinePlace[] {
  return places.map((p) => {
    if (p.kind !== "module" || p.module.id !== moduleId) return p
    const chapters = [...p.chapters]
    const [moved] = chapters.splice(from, 1)
    if (!moved) return p
    chapters.splice(to, 0, moved)
    return { ...p, chapters }
  })
}

/**
 * File a lesson under a module, at that module's end — or, with `null`, take
 * it out of its module, where it stays right after the module it left
 * rather than jumping to the end of the course.
 */
export function fileLesson(places: OutlinePlace[], chapterId: string, moduleId: string | null): OutlinePlace[] {
  let lesson: Chapter | undefined
  let leftModule: string | null = null
  const without: OutlinePlace[] = []
  for (const p of places) {
    if (p.kind === "lesson") {
      if (p.chapter.id === chapterId) lesson = p.chapter
      else without.push(p)
      continue
    }
    const found = p.chapters.find((c) => c.id === chapterId)
    if (found) {
      lesson = found
      leftModule = p.module.id
      without.push({ ...p, chapters: p.chapters.filter((c) => c.id !== chapterId) })
    } else {
      without.push(p)
    }
  }
  if (!lesson || leftModule === moduleId) return places
  if (moduleId === null) {
    const at = without.findIndex((p) => p.kind === "module" && p.module.id === leftModule)
    without.splice(at + 1, 0, { kind: "lesson", chapter: { ...lesson, module_id: null } })
    return without
  }
  const moved = lesson
  return without.map((p) =>
    p.kind === "module" && p.module.id === moduleId
      ? { ...p, chapters: [...p.chapters, { ...moved, module_id: moduleId }] }
      : p,
  )
}

/** The body of `PUT /courses/{id}/outline`. */
export function outlinePayload(places: OutlinePlace[]): { module_id: string | null; chapter_ids: string[] }[] {
  return places.map((p) =>
    p.kind === "module"
      ? { module_id: p.module.id, chapter_ids: p.chapters.map((c) => c.id) }
      : { module_id: null, chapter_ids: [p.chapter.id] },
  )
}

/**
 * The course with `places` written into it, numbered exactly as the server
 * numbers them (`number_outline`): one counter over the course in reading
 * order — a module, then its lessons, then the next place. So the screen
 * holds what the server will hold, without a reload.
 */
export function applyOutline(course: Course, places: OutlinePlace[]): Course {
  let n = 0
  const modules: Module[] = []
  const loose: Chapter[] = []
  for (const p of places) {
    if (p.kind === "module") {
      const order = n++
      const chapters = p.chapters.map((c) => ({ ...c, module_id: p.module.id, order_index: n++ }))
      modules.push({ ...p.module, order_index: order, chapters })
    } else {
      loose.push({ ...p.chapter, module_id: null, order_index: n++ })
    }
  }
  return { ...course, modules, chapters: loose }
}
