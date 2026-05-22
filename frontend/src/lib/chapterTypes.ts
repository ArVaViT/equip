import {
  ClipboardList,
  FileText,
  GraduationCap,
  HelpCircle,
  type LucideIcon,
} from "lucide-react"

/**
 * Single source of truth for the user-facing chapter types. The backend mirror
 * lives at ``backend/app/schemas/course.py`` (``CHAPTER_TYPES`` literal); if you
 * add a type, update both sides *and* the Postgres ``chapters_chapter_type_check``
 * constraint.
 *
 * ``video`` / ``audio`` / ``mixed`` / ``content`` / ``discussion`` were
 * collapsed into block-based ``reading`` by migration 024 — every
 * content-shaped chapter is now a sequence of typed blocks. They live on in
 * ``LEGACY_ALIASES`` below so stale client caches don't blow up.
 */
export const CHAPTER_TYPES = [
  "reading",
  "quiz",
  "exam",
  "assignment",
] as const

export type ChapterType = (typeof CHAPTER_TYPES)[number]

type ChapterTypeMeta = {
  icon: LucideIcon
  /** Tailwind pill classes (editorial: muted surface, neutral text). */
  color: string
  /** Compact badge variant — same editorial treatment as ``color``. */
  badgeColor: string
}

// Editorial palette: chapter type is communicated through label + icon, not
// colour. Using a single muted token keeps the UI calm and consistent across
// light/dark and matches the rest of the token-based design system.
const PILL = "bg-muted text-muted-foreground"

// ``label`` and ``description`` are NOT on this map — they're rendered via
// the i18n keys under ``chapterTypes.{reading|quiz|exam|assignment}`` so
// RU and EN stay in lockstep. The map is only the locale-neutral icon +
// style metadata.
export const CHAPTER_TYPE_META: Record<ChapterType, ChapterTypeMeta> = {
  reading: { icon: FileText, color: PILL, badgeColor: PILL },
  quiz: { icon: HelpCircle, color: PILL, badgeColor: PILL },
  exam: { icon: GraduationCap, color: PILL, badgeColor: PILL },
  assignment: { icon: ClipboardList, color: PILL, badgeColor: PILL },
}

/** Chapter types whose completion gates the next chapter when ``is_locked`` is on. */
const GRADABLE_CHAPTER_TYPES: ReadonlySet<ChapterType> = new Set([
  "quiz",
  "exam",
  "assignment",
])

const LEGACY_ALIASES: Record<string, ChapterType> = {
  // All collapsed into reading by migration 024. Clients may still have
  // stale caches; normalise so the UI never sees the old values.
  content: "reading",
  discussion: "reading",
  video: "reading",
  audio: "reading",
  mixed: "reading",
}

/**
 * Coerce any string coming from the API to a known ``ChapterType``. Falls back
 * to ``"reading"`` for anything unrecognised so the UI always has something to
 * render.
 */
export function normalizeChapterType(raw: string | null | undefined): ChapterType {
  if (!raw) return "reading"
  if ((CHAPTER_TYPES as readonly string[]).includes(raw)) return raw as ChapterType
  return LEGACY_ALIASES[raw] ?? "reading"
}

export function getChapterTypeMeta(raw: string | null | undefined): ChapterTypeMeta {
  return CHAPTER_TYPE_META[normalizeChapterType(raw)]
}

export function isGradableChapterType(raw: string | null | undefined): boolean {
  return GRADABLE_CHAPTER_TYPES.has(normalizeChapterType(raw))
}

// Static i18n key lookups so callers ``t(CHAPTER_TYPE_LABEL_KEYS[type])`` —
// instead of ``t(`chapterTypes.${type}.label`)`` — and the keyCoverage
// test can see every key as a literal at scan time. Per docs/I18N.md:
// "Resist the temptation to write t(`prefix.${variable}`)".
export const CHAPTER_TYPE_LABEL_KEYS: Record<ChapterType, string> = {
  reading: "chapterTypes.reading.label",
  quiz: "chapterTypes.quiz.label",
  exam: "chapterTypes.exam.label",
  assignment: "chapterTypes.assignment.label",
}

export const CHAPTER_TYPE_DESCRIPTION_KEYS: Record<ChapterType, string> = {
  reading: "chapterTypes.reading.description",
  quiz: "chapterTypes.quiz.description",
  exam: "chapterTypes.exam.description",
  assignment: "chapterTypes.assignment.description",
}
