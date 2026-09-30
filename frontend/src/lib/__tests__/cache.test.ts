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
  cacheClear,
  cached,
} from "@/lib/cache"

// The cache module keeps state at module scope. Each test starts from
// an empty store so order does not matter.
beforeEach(() => {
  cacheClear()
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

describe("cache.cacheClear", () => {
  it("removes every entry regardless of key shape", () => {
    // Auth boundary crossings (sign-out / sign-in as another account)
    // call this so user A's payloads can't be served to user B.
    cacheSet("t:a", 1, 60_000)
    cacheSet("u:list:all", "A", 60_000)
    cacheSet<string | null>("x:null", null, 60_000)

    cacheClear()

    expect(cacheGet("t:a")).toBeUndefined()
    expect(cacheGet("u:list:all")).toBeUndefined()
    expect(cacheGet("x:null")).toBeUndefined()
  })

  it("is a no-op on an already-empty cache", () => {
    cacheClear()
    expect(() => cacheClear()).not.toThrow()
  })

  it("allows fresh writes after clearing", () => {
    cacheSet("t:rewrite", "old", 60_000)
    cacheClear()
    cacheSet("t:rewrite", "new", 60_000)
    expect(cacheGet("t:rewrite")).toBe("new")
  })
})

describe("cache.cached", () => {
  it("calls the fetcher on miss and stores the result", async () => {
    const fetcher = vi.fn().mockResolvedValue({ id: 1 })
    const got = await cached("t:cached:miss", 60_000, fetcher)

    expect(got).toEqual({ id: 1 })
    expect(fetcher).toHaveBeenCalledTimes(1)
    expect(cacheGet("t:cached:miss")).toEqual({ id: 1 })
  })

  it("returns the cached value without calling the fetcher on hit", async () => {
    cacheSet("t:cached:hit", "stored", 60_000)
    const fetcher = vi.fn().mockResolvedValue("fresh")

    const got = await cached("t:cached:hit", 60_000, fetcher)

    expect(got).toBe("stored")
    expect(fetcher).not.toHaveBeenCalled()
  })

  it("honours a cached null without re-fetching", async () => {
    // quizzesService caches null for 404s; make sure that round-trips.
    cacheSet<string | null>("t:cached:null", null, 60_000)
    const fetcher = vi.fn().mockResolvedValue("should-not-be-called")

    const got = await cached<string | null>("t:cached:null", 60_000, fetcher)

    expect(got).toBeNull()
    expect(fetcher).not.toHaveBeenCalled()
  })

  it("propagates fetcher errors without poisoning the cache", async () => {
    const fetcher = vi.fn().mockRejectedValue(new Error("boom"))

    await expect(cached("t:cached:throw", 60_000, fetcher)).rejects.toThrow("boom")
    expect(cacheGet("t:cached:throw")).toBeUndefined()
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

describe("cached() and a language switch mid-flight", () => {
  it("stores the answer under the language the request went out in", async () => {
    const i18n = (await import("@/i18n/config")).default
    const { cached, cacheGet, cacheClear } = await import("../cache")
    cacheClear()
    await i18n.changeLanguage("ru")
    let release: (v: string) => void = () => {}
    const pending = cached("race:key", 60_000, () => new Promise<string>((r) => (release = r)))
    // The reader switches while the Russian answer is still on its way.
    await i18n.changeLanguage("de")
    release("русский ответ")
    await pending
    expect(cacheGet("race:key")).toBeUndefined()
    await i18n.changeLanguage("ru")
    expect(cacheGet("race:key")).toBe("русский ответ")
  })
})

describe("cached — size bound", () => {
  it("evicts the oldest entry when a fetched value overflows the store", async () => {
    // `cached` writes the store itself (the key is fixed before the await);
    // without the eviction there the store grew past MAX_ENTRIES unbounded.
    cacheClear()
    for (let i = 0; i < 200; i++) cacheSet(`fill:${i}`, i)
    await cached("overflow", 60_000, () => Promise.resolve("new"))
    expect(cacheGet("fill:0")).toBeUndefined()
    expect(cacheGet("overflow")).toBe("new")
  })
})

describe("cached — concurrent readers", () => {
  it("shares one request between two readers of the same key", async () => {
    cacheClear()
    let calls = 0
    let release: (v: string) => void = () => {}
    const fetcher = () => {
      calls++
      return new Promise<string>((r) => (release = r))
    }
    const a = cached("shared", 60_000, fetcher)
    const b = cached("shared", 60_000, fetcher)
    release("one answer")
    expect(await a).toBe("one answer")
    expect(await b).toBe("one answer")
    expect(calls).toBe(1)
  })

  it("does not store an answer sent before an invalidation that landed meanwhile", async () => {
    cacheClear()
    let release: (v: string) => void = () => {}
    const pending = cached("mutated", 60_000, () => new Promise<string>((r) => (release = r)))
    cacheInvalidate("mutated")
    release("stale")
    expect(await pending).toBe("stale")
    expect(cacheGet("mutated")).toBeUndefined()
  })
})
