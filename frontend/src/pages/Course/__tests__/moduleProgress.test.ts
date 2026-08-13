import { describe, expect, it } from "vitest"
import { isChapterComplete, isChapterLocked } from "../moduleProgress"

const CH = { id: "ch-2", is_locked: true }
const PREV = { id: "ch-1" }

describe("isChapterComplete", () => {
  it("marks a chapter the student finished", () => {
    expect(isChapterComplete(new Set(["ch-2"]), CH, true)).toBe(true)
  })

  it("claims nothing when progress could not be loaded", () => {
    // Not the same as "finished nothing". A student who completed this module
    // used to meet a page of empty circles because a request timed out.
    expect(isChapterComplete(null, CH, true)).toBe(false)
  })
})

describe("isChapterLocked", () => {
  it("locks a gated chapter whose predecessor is unfinished", () => {
    expect(isChapterLocked(new Set(), CH, PREV, true)).toBe(true)
  })

  it("opens it once the predecessor is done", () => {
    expect(isChapterLocked(new Set(["ch-1"]), CH, PREV, true)).toBe(false)
  })

  it("fails OPEN when progress is unknown", () => {
    // The bug: `!completed.has(prev)` on an empty fallback set is `true`, so a
    // failed request walled a student out of chapters they had earned. The
    // server is the real gate; a client guess that denies somebody their own
    // progress is the worse of the two ways to be wrong.
    expect(isChapterLocked(null, CH, PREV, true)).toBe(false)
  })

  it("never locks a chapter that is not gated", () => {
    expect(isChapterLocked(new Set(), { id: "ch-2" }, PREV, true)).toBe(false)
  })
})
