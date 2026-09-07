/**
 * The chapter half of the courses service.
 *
 * A lesson belongs to a course; the module is a field on it. Two things had
 * to change and both are easy to get wrong from the outside, so they are
 * pinned here rather than left to a screen to discover:
 *
 *  - the addresses, which no longer carry a module — and the `PUT` body,
 *    where `module_id` is three-valued and an accidental `null` silently
 *    pulls a lesson out of its module;
 *  - the cache, which used to be nudged by the (course, module) pair. A
 *    lesson in no module has no such pair, and a lesson leaving a module
 *    left a stale copy of itself behind in the module it left.
 */

import { beforeEach, describe, expect, it, vi } from "vitest"

// ``services/api`` builds the supabase client at module load from
// ``VITE_SUPABASE_*``. Mocked before any other import so the suite never
// depends on the real env vars.
vi.mock("@/lib/supabase", () => ({
  supabase: {
    auth: {
      getSession: vi.fn().mockResolvedValue({ data: { session: null } }),
      refreshSession: vi.fn(),
      signOut: vi.fn(),
      onAuthStateChange: vi
        .fn()
        .mockReturnValue({ data: { subscription: { unsubscribe: vi.fn() } } }),
    },
  },
}))

vi.mock("@/services/api", () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
}))

import api from "@/services/api"
import { cacheClear, cacheGet, cacheSet, CACHE_TTL } from "@/lib/cache"
import { coursesService } from "@/services/courses"
import type { Chapter } from "@/types"

const mockApi = vi.mocked(api)

const CHAPTER: Chapter = {
  id: "ch-1",
  course_id: "c-1",
  module_id: null,
  title: "Первый урок",
  order_index: 0,
  chapter_type: "reading",
  requires_completion: false,
  is_locked: false,
}

/** Fill the cache with everything a chapter mutation could make stale. */
function primeCourseCache(): void {
  cacheSet("courses:detail:c-1", { id: "c-1" }, CACHE_TTL.THREE_MINUTES)
  cacheSet("courses:module:c-1:m-1", { id: "m-1" }, CACHE_TTL.THREE_MINUTES)
  cacheSet("courses:module:c-1:m-2", { id: "m-2" }, CACHE_TTL.THREE_MINUTES)
  cacheSet("courses:detail:c-2", { id: "c-2" }, CACHE_TTL.THREE_MINUTES)
  cacheSet("courses:module:c-2:m-9", { id: "m-9" }, CACHE_TTL.THREE_MINUTES)
}

beforeEach(() => {
  vi.clearAllMocks()
  cacheClear()
  mockApi.post.mockResolvedValue({ data: CHAPTER })
  mockApi.put.mockResolvedValue({ data: CHAPTER })
  mockApi.get.mockResolvedValue({ data: CHAPTER })
  mockApi.delete.mockResolvedValue({ data: undefined })
})

describe("createCourseChapter", () => {
  it("writes the lesson into the course, with no module in the address", () => {
    return coursesService
      .createCourseChapter("c-1", { title: "Первый урок", chapter_type: "reading" })
      .then((created) => {
        expect(mockApi.post).toHaveBeenCalledWith("/courses/c-1/chapters", {
          title: "Первый урок",
          chapter_type: "reading",
        })
        expect(created).toEqual(CHAPTER)
      })
  })

  it("sends no module_id — the create endpoint refuses keys it does not know", () => {
    return coursesService.createCourseChapter("c-1", { title: "Первый урок" }).then(() => {
      const [, body] = mockApi.post.mock.calls[0]!
      expect(Object.keys(body as object)).toEqual(["title"])
    })
  })

  it("makes the whole course stale, not one module of it", () => {
    primeCourseCache()
    return coursesService.createCourseChapter("c-1", { title: "Первый урок" }).then(() => {
      expect(cacheGet("courses:detail:c-1")).toBeUndefined()
      expect(cacheGet("courses:module:c-1:m-1")).toBeUndefined()
      expect(cacheGet("courses:module:c-1:m-2")).toBeUndefined()
      // …and nothing beyond it.
      expect(cacheGet("courses:detail:c-2")).toBeDefined()
      expect(cacheGet("courses:module:c-2:m-9")).toBeDefined()
    })
  })
})

describe("getChapterForEdit", () => {
  it("fetches one lesson by its id, without asking for the module around it", () => {
    return coursesService.getChapterForEdit("c-1", "ch-1").then((chapter) => {
      expect(mockApi.get).toHaveBeenCalledWith("/courses/c-1/chapters/ch-1")
      expect(chapter).toEqual(CHAPTER)
    })
  })

  it("does not answer twice from a cache", () => {
    // The endpoint answers in the course's source language. Holding that
    // under a key is how a teacher's own words and their translation end up
    // clobbering each other, so this read is uncached — like its course and
    // module twins.
    return coursesService
      .getChapterForEdit("c-1", "ch-1")
      .then(() => coursesService.getChapterForEdit("c-1", "ch-1"))
      .then(() => {
        expect(mockApi.get).toHaveBeenCalledTimes(2)
      })
  })
})

describe("updateCourseChapter", () => {
  it("edits a lesson at its course address", () => {
    return coursesService
      .updateCourseChapter("c-1", "ch-1", { title: "Новое название" })
      .then(() => {
        expect(mockApi.put).toHaveBeenCalledWith("/courses/c-1/chapters/ch-1", {
          title: "Новое название",
        })
      })
  })

  it("leaves the grouping alone when the caller says nothing about it", () => {
    // Absent means "unchanged" on the wire. A `null` here would quietly pull
    // the lesson out of its module every time a teacher renamed it.
    return coursesService
      .updateCourseChapter("c-1", "ch-1", { title: "Новое название" })
      .then(() => {
        const [, body] = mockApi.put.mock.calls[0]!
        expect(body).not.toHaveProperty("module_id")
      })
  })

  it("puts a lesson into a module", () => {
    return coursesService
      .updateCourseChapter("c-1", "ch-1", { module_id: "m-2" })
      .then(() => {
        expect(mockApi.put).toHaveBeenCalledWith("/courses/c-1/chapters/ch-1", {
          module_id: "m-2",
        })
      })
  })

  it("takes a lesson out of its module with an explicit null", () => {
    return coursesService
      .updateCourseChapter("c-1", "ch-1", { module_id: null })
      .then(() => {
        const [, body] = mockApi.put.mock.calls[0]!
        expect(body).toEqual({ module_id: null })
        expect(body).toHaveProperty("module_id")
      })
  })

  it("makes both sides of a move stale, because it cannot know the old one", () => {
    primeCourseCache()
    return coursesService.updateCourseChapter("c-1", "ch-1", { module_id: "m-2" }).then(() => {
      expect(cacheGet("courses:detail:c-1")).toBeUndefined()
      // The module it left is as stale as the one it joined, and the caller
      // never named it.
      expect(cacheGet("courses:module:c-1:m-1")).toBeUndefined()
      expect(cacheGet("courses:module:c-1:m-2")).toBeUndefined()
      expect(cacheGet("courses:detail:c-2")).toBeDefined()
    })
  })
})

describe("deleteCourseChapter", () => {
  it("deletes at the course address and makes the course stale", () => {
    primeCourseCache()
    return coursesService.deleteCourseChapter("c-1", "ch-1").then(() => {
      expect(mockApi.delete).toHaveBeenCalledWith("/courses/c-1/chapters/ch-1")
      expect(cacheGet("courses:detail:c-1")).toBeUndefined()
      expect(cacheGet("courses:module:c-1:m-1")).toBeUndefined()
      expect(cacheGet("courses:detail:c-2")).toBeDefined()
    })
  })
})

describe("the module-shaped calls the screens still make", () => {
  it("still address a lesson through its module", () => {
    return coursesService
      .createChapter("c-1", "m-1", { title: "Урок" })
      .then(() => coursesService.updateChapter("c-1", "m-1", "ch-1", { title: "Урок" }))
      .then(() => coursesService.deleteChapter("c-1", "m-1", "ch-1"))
      .then(() => {
        expect(mockApi.post).toHaveBeenCalledWith("/courses/c-1/modules/m-1/chapters", {
          title: "Урок",
        })
        expect(mockApi.put).toHaveBeenCalledWith(
          "/courses/c-1/modules/m-1/chapters/ch-1",
          { title: "Урок" },
        )
        expect(mockApi.delete).toHaveBeenCalledWith("/courses/c-1/modules/m-1/chapters/ch-1")
      })
  })

  it("clear the course too, so an old screen cannot leave a new one stale", () => {
    // Both kinds of call reach the same lessons. If the module-shaped ones
    // kept clearing only their own pair, a course detail read right after
    // one of them would still be holding the lesson as it was.
    primeCourseCache()
    return coursesService.updateChapter("c-1", "m-1", "ch-1", { title: "Урок" }).then(() => {
      expect(cacheGet("courses:detail:c-1")).toBeUndefined()
      expect(cacheGet("courses:module:c-1:m-1")).toBeUndefined()
      expect(cacheGet("courses:module:c-1:m-2")).toBeUndefined()
      expect(cacheGet("courses:detail:c-2")).toBeDefined()
    })
  })
})
