import { describe, it, expect } from "vitest"
import {
  makeChapterSchema,
  makeCourseSchema,
  makeModuleSchema,
  makeProfileSchema,
} from "../course"
import { CHAPTER_TYPES } from "@/lib/chapterTypes"

// Tests are locale-agnostic, so building the schema once at module scope
// matches the previous static-export semantics without re-running the
// factory per assertion.
const courseSchema = makeCourseSchema()
const moduleSchema = makeModuleSchema()
const chapterSchema = makeChapterSchema()
const profileSchema = makeProfileSchema()

describe("courseSchema", () => {
  it("accepts a valid minimal course", () => {
    const result = courseSchema.safeParse({ title: "Genesis Overview" })
    expect(result.success).toBe(true)
  })

  it("rejects an empty title", () => {
    const result = courseSchema.safeParse({ title: "" })
    expect(result.success).toBe(false)
  })

  it("rejects a title longer than 300 characters", () => {
    const result = courseSchema.safeParse({ title: "a".repeat(301) })
    expect(result.success).toBe(false)
  })

  it("treats empty-string optional fields as valid", () => {
    const result = courseSchema.safeParse({
      title: "Valid",
      description: "",
    })
    expect(result.success).toBe(true)
  })

  it("rejects descriptions over 10k characters", () => {
    const result = courseSchema.safeParse({
      title: "Valid",
      description: "a".repeat(10_001),
    })
    expect(result.success).toBe(false)
  })

  it("trims whitespace-only titles before the min check", () => {
    const result = courseSchema.safeParse({ title: "   " })
    expect(result.success).toBe(false)
  })
})

describe("moduleSchema", () => {
  it("accepts a minimal module", () => {
    const result = moduleSchema.safeParse({ title: "Module 1" })
    expect(result.success).toBe(true)
  })

  it("defaults order_index to 0 when omitted", () => {
    const result = moduleSchema.safeParse({ title: "Module 1" })
    if (!result.success) throw new Error("expected success")
    expect(result.data.order_index).toBe(0)
  })

  it("rejects negative order_index", () => {
    const result = moduleSchema.safeParse({ title: "Module 1", order_index: -1 })
    expect(result.success).toBe(false)
  })

  it("rejects non-integer order_index", () => {
    const result = moduleSchema.safeParse({ title: "Module 1", order_index: 1.5 })
    expect(result.success).toBe(false)
  })

  it("accepts a valid ISO datetime for due_date", () => {
    const result = moduleSchema.safeParse({
      title: "Module 1",
      due_date: "2026-12-31T23:59:59Z",
    })
    expect(result.success).toBe(true)
  })

  it("rejects non-ISO due_date", () => {
    const result = moduleSchema.safeParse({
      title: "Module 1",
      due_date: "tomorrow",
    })
    expect(result.success).toBe(false)
  })
})

describe("chapterSchema", () => {
  it("accepts the documented chapter types", () => {
    for (const type of CHAPTER_TYPES) {
      const result = chapterSchema.safeParse({ title: "C", chapter_type: type })
      expect(result.success).toBe(true)
    }
  })

  it("rejects unknown chapter_type values", () => {
    const result = chapterSchema.safeParse({
      title: "C",
      chapter_type: "podcast",
    })
    expect(result.success).toBe(false)
  })

  it("defaults boolean toggles to false", () => {
    const result = chapterSchema.safeParse({ title: "C" })
    if (!result.success) throw new Error("expected success")
    expect(result.data.is_locked).toBe(false)
    expect(result.data.requires_completion).toBe(false)
  })

})

describe("profileSchema", () => {
  it("rejects a single-character name", () => {
    expect(profileSchema.safeParse({ full_name: "A" }).success).toBe(false)
  })

  it("accepts a normal name", () => {
    expect(profileSchema.safeParse({ full_name: "Jane Doe" }).success).toBe(true)
  })

  it("trims before the min-length check", () => {
    expect(profileSchema.safeParse({ full_name: " a " }).success).toBe(false)
  })
})
