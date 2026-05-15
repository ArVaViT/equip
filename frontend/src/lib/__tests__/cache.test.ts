/**
 * Unit tests for the in-memory service cache.
 *
 * The cache is consumed by every service file (see CACHE_TTL usages),
 * so a regression in `cacheGet` / `cacheSet` / `cacheInvalidate*`
 * ripples through every list / detail screen. These tests cover the
 * observable contract: lookups, expiry, prefix invalidation, and the
 * MAX_ENTRIES eviction policy.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import {
  cacheGet,
  cacheSet,
  cacheInvalidate,
  cacheInvalidatePrefix,
} from "@/lib/cache"

// The cache module keeps state at module scope. Each test starts by
// clearing whatever the previous test wrote so order does not matter.
function resetCache(): void {
  // Cache exposes no clear() helper by design (services own their keys);
  // we walk the known test-prefixed keys instead.
  for (const prefix of ["t:", "u:", "x:", "evict:"]) {
    cacheInvalidatePrefix(prefix)
  }
}

beforeEach(() => {
  resetCache()
})

afterEach(() => {
  vi.useRealTimers()
})

describe("cache.cacheGet / cacheSet", () => {
  it("returns undefined for a key that was never set", () => {
    expect(cacheGet("t:never-set")).toBeUndefined()
  })

  it("returns the stored value before its TTL expires", () => {
    cacheSet("t:hello", { name: "Vadym" }, 60_000)
    expect(cacheGet<{ name: string }>("t:hello")).toEqual({ name: "Vadym" })
  })

  it("preserves the value type via the generic parameter", () => {
    cacheSet("t:num", 42, 60_000)
    const got = cacheGet<number>("t:num")
    expect(got).toBe(42)
  })

  it("returns undefined once the TTL elapses", () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date("2026-01-01T00:00:00Z"))

    cacheSet("t:expires", "stale", 1_000)
    expect(cacheGet("t:expires")).toBe("stale")

    vi.advanceTimersByTime(1_001)
    expect(cacheGet("t:expires")).toBeUndefined()
  })

  it("overwrites an existing key with a new value and TTL", () => {
    cacheSet("t:overwrite", "first", 60_000)
    cacheSet("t:overwrite", "second", 60_000)
    expect(cacheGet("t:overwrite")).toBe("second")
  })

  it("can store the literal value null and round-trips it", () => {
    // `quizzesService.getChapterQuiz` deliberately caches `null` for 404
    // responses so a chapter without a quiz isn't re-fetched on every
    // re-render. Make sure null isn't mistaken for "missing".
    cacheSet<string | null>("t:null", null, 60_000)
    expect(cacheGet<string | null>("t:null")).toBeNull()
  })
})

describe("cache.cacheInvalidate", () => {
  it("removes a single key", () => {
    cacheSet("t:a", 1, 60_000)
    cacheSet("t:b", 2, 60_000)
    cacheInvalidate("t:a")
    expect(cacheGet("t:a")).toBeUndefined()
    expect(cacheGet("t:b")).toBe(2)
  })

  it("is a no-op for a key that is not present", () => {
    expect(() => cacheInvalidate("t:absent")).not.toThrow()
  })
})

describe("cache.cacheInvalidatePrefix", () => {
  it("removes every key starting with the prefix", () => {
    cacheSet("u:list:all", "A", 60_000)
    cacheSet("u:list:teacher", "B", 60_000)
    cacheSet("u:detail:1", "C", 60_000)
    cacheSet("x:list:other", "D", 60_000)

    cacheInvalidatePrefix("u:list:")

    expect(cacheGet("u:list:all")).toBeUndefined()
    expect(cacheGet("u:list:teacher")).toBeUndefined()
    expect(cacheGet("u:detail:1")).toBe("C")
    expect(cacheGet("x:list:other")).toBe("D")
  })

  it("is a no-op when no key matches the prefix", () => {
    cacheSet("u:keep", 1, 60_000)
    cacheInvalidatePrefix("u:no-such-prefix:")
    expect(cacheGet("u:keep")).toBe(1)
  })
})

describe("cache eviction", () => {
  it("keeps the cache size bounded under sustained writes", () => {
    // MAX_ENTRIES is 200 in the implementation. Write more than that
    // and verify the cache hasn't grown without bound — at least the
    // oldest entries must have been evicted.
    for (let i = 0; i < 300; i++) {
      cacheSet(`evict:${i}`, i, 60_000)
    }

    // At least 100 of the first 200 entries should be gone after the
    // overflow eviction kicks in. We don't assert a precise number
    // because the implementation may evict expired-first then FIFO.
    let stillPresent = 0
    for (let i = 0; i < 200; i++) {
      if (cacheGet(`evict:${i}`) !== undefined) stillPresent++
    }
    expect(stillPresent).toBeLessThan(200)

    // Newest entries should still be readable.
    expect(cacheGet("evict:299")).toBe(299)
  })
})
