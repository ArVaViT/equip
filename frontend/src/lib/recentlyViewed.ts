/**
 * "Recently viewed courses" — a tiny localStorage-backed MRU list of the
 * last few course IDs a student opened, used to render a quick-return row
 * on the dashboard. Pure frontend: no backend, no PII (just course IDs +
 * timestamps). Stale / no-longer-enrolled IDs are filtered out at render
 * time against the user's known courses, so a deleted or unenrolled
 * course silently drops off.
 *
 * Not user-scoped on purpose: course IDs are opaque UUIDs that carry no
 * personal data, and the dashboard always intersects this list with the
 * signed-in user's actual enrollments before showing anything — so a
 * shared device never leaks one account's course list into another's row.
 */

const STORAGE_KEY = "equip.recently-viewed.courses"
const MAX_ENTRIES = 5

export interface RecentCourse {
  id: string
  /** Epoch millis of the most recent open. */
  ts: number
}

function read(): RecentCourse[] {
  if (typeof window === "undefined") return []
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    if (!raw) return []
    const parsed: unknown = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    return parsed
      .filter(
        (e): e is RecentCourse =>
          !!e &&
          typeof e === "object" &&
          typeof (e as RecentCourse).id === "string" &&
          typeof (e as RecentCourse).ts === "number",
      )
      .sort((a, b) => b.ts - a.ts)
      .slice(0, MAX_ENTRIES)
  } catch {
    // Corrupt JSON or denied storage (private browsing): treat as empty.
    return []
  }
}

/** The most-recent-first list of recently opened course IDs. */
export function getRecentCourses(): RecentCourse[] {
  return read()
}

/**
 * Record a course open. Moves the id to the front (de-duplicating), caps
 * the list at ``MAX_ENTRIES``, and is a no-op when storage is unavailable.
 * Safe to call from any course/chapter mount.
 */
export function recordCourseView(courseId: string): void {
  if (typeof window === "undefined") return
  if (!courseId) return
  try {
    const now = Date.now()
    const existing = read().filter((e) => e.id !== courseId)
    const next = [{ id: courseId, ts: now }, ...existing].slice(0, MAX_ENTRIES)
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next))
  } catch {
    // localStorage can be denied / full; recently-viewed is best-effort.
  }
}
