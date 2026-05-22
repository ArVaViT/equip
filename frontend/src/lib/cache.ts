const DEFAULT_TTL = 5 * 60 * 1000
const MAX_ENTRIES = 200

/**
 * Named TTLs used by service caches. Picking from this menu keeps the
 * meaning of each value visible at the call site — "this list mutates
 * fast, hold it briefly" beats `30 * 1000`. Values are in milliseconds.
 */
export const CACHE_TTL = {
  /** Fast-moving data (live analytics, in-flight student progress). */
  THIRTY_SECONDS: 30 * 1000,
  /** Default for per-user lists that change after writes (enrollments, grades, calendar). */
  ONE_MINUTE: 60 * 1000,
  /** Reference data that updates occasionally (announcements, course lists, cohorts). */
  TWO_MINUTES: 2 * 60 * 1000,
  /** Stable detail views (course detail, module detail). */
  THREE_MINUTES: 3 * 60 * 1000,
} as const

interface CacheEntry<T = unknown> {
  value: T
  expiresAt: number
}

const store = new Map<string, CacheEntry>()

function evictExpired(): void {
  const now = Date.now()
  for (const [key, entry] of store) {
    if (now > entry.expiresAt) store.delete(key)
  }
}

function evictIfNeeded(): void {
  if (store.size <= MAX_ENTRIES) return
  evictExpired()
  if (store.size <= MAX_ENTRIES) return

  const overflow = store.size - MAX_ENTRIES
  const keys = store.keys()
  for (let i = 0; i < overflow; i++) {
    const { value, done } = keys.next()
    if (done) break
    store.delete(value)
  }
}

export function cacheGet<T = unknown>(key: string): T | undefined {
  const entry = store.get(key)
  if (!entry) return undefined
  if (Date.now() > entry.expiresAt) {
    store.delete(key)
    return undefined
  }
  return entry.value as T
}

export function cacheSet<T = unknown>(key: string, value: T, ttlMs: number = DEFAULT_TTL): void {
  store.set(key, { value, expiresAt: Date.now() + ttlMs })
  evictIfNeeded()
}

export function cacheInvalidate(key: string): void {
  store.delete(key)
}

export function cacheInvalidatePrefix(prefix: string): void {
  for (const key of store.keys()) {
    if (key.startsWith(prefix)) store.delete(key)
  }
}

/**
 * Cache-miss-then-fetch helper. Services do this dance constantly:
 *
 *   const cached = cacheGet<T>(key)
 *   if (cached !== undefined) return cached
 *   const fresh = await fetcher()
 *   cacheSet(key, fresh, ttlMs)
 *   return fresh
 *
 * which spreads the cache key, the TTL, and the fetcher across four
 * statements per read endpoint. `cached()` collapses that into one
 * expression so the call site only mentions the meaningful inputs.
 *
 * Uses `cacheGet` (which already handles expiry + null round-trip), so
 * cached `null` values are honoured — `quizzesService.getChapterQuiz`
 * relies on caching 404s as `null` to avoid re-fetching missing quizzes.
 */
export async function cached<T>(
  key: string,
  ttlMs: number,
  fetcher: () => Promise<T>,
): Promise<T> {
  const hit = cacheGet<T>(key)
  if (hit !== undefined) return hit
  const fresh = await fetcher()
  cacheSet(key, fresh, ttlMs)
  return fresh
}
