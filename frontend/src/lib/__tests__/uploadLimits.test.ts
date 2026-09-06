import { describe, expect, it } from "vitest"

import {
  acceptAttribute,
  COURSE_ASSETS,
  COURSE_MATERIALS,
  isHeic,
  MB,
  resolveContentType,
} from "@/lib/uploadLimits"

/**
 * These mirror `supabase/migrations/20260227031449_create_storage_buckets.sql`.
 * The client used to promise more than the bucket — 10 MB against 5,
 * ``.mp4`` against a bucket that only knows ``audio/mp4`` — and a teacher's
 * file passed every check on screen and failed in English on the server.
 */
describe("bucket specs match the migration", () => {
  it("course-assets: 5 MB, five image types", () => {
    expect(COURSE_ASSETS.maxBytes).toBe(5 * MB)
    expect(COURSE_ASSETS.mimeTypes).toEqual([
      "image/jpeg",
      "image/png",
      "image/webp",
      "image/gif",
      "image/svg+xml",
    ])
  })

  it("course-materials: 50 MB, documents and audio, no video", () => {
    expect(COURSE_MATERIALS.maxBytes).toBe(50 * MB)
    expect(COURSE_MATERIALS.mimeTypes).toContain("audio/mp4")
    expect(COURSE_MATERIALS.mimeTypes).not.toContain("video/mp4")
  })

  it("the picker filter does not offer .mp4 and does offer .m4a", () => {
    const accept = acceptAttribute(COURSE_MATERIALS)
    expect(accept).not.toContain(".mp4")
    expect(accept).toContain(".m4a")
    expect(accept).toContain("application/pdf")
  })
})

describe("resolveContentType", () => {
  it("folds a browser's alias onto the bucket's spelling", () => {
    expect(resolveContentType({ name: "memo.m4a", type: "audio/x-m4a" }, COURSE_MATERIALS)).toBe("audio/mp4")
    expect(resolveContentType({ name: "song.mp3", type: "audio/mp3" }, COURSE_MATERIALS)).toBe("audio/mpeg")
    expect(resolveContentType({ name: "photo.jpg", type: "image/jpg" }, COURSE_ASSETS)).toBe("image/jpeg")
  })

  it("falls back to the extension only when the browser gave no type", () => {
    expect(resolveContentType({ name: "deck.pptx", type: "" }, COURSE_MATERIALS)).toBe(
      "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    )
    expect(resolveContentType({ name: "deck.pptx", type: "application/octet-stream" }, COURSE_MATERIALS)).toBe(
      "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    )
    // A confident wrong type is not second-guessed by the extension.
    expect(resolveContentType({ name: "deck.pptx", type: "video/mp4" }, COURSE_MATERIALS)).toBeNull()
  })

  it("ignores a charset parameter", () => {
    expect(resolveContentType({ name: "a.txt", type: "text/plain;charset=UTF-8" }, COURSE_MATERIALS)).toBe("text/plain")
  })

  it("answers null for what the bucket will refuse", () => {
    expect(resolveContentType({ name: "clip.mp4", type: "video/mp4" }, COURSE_MATERIALS)).toBeNull()
    expect(resolveContentType({ name: "photo.heic", type: "image/heic" }, COURSE_ASSETS)).toBeNull()
    expect(resolveContentType({ name: "mystery", type: "" }, COURSE_MATERIALS)).toBeNull()
  })
})

describe("isHeic", () => {
  it("recognises an iPhone photo by type or by extension", () => {
    expect(isHeic({ name: "IMG_0001.HEIC", type: "image/heic" })).toBe(true)
    expect(isHeic({ name: "IMG_0001.heif", type: "" })).toBe(true)
    expect(isHeic({ name: "IMG_0001.jpg", type: "image/jpeg" })).toBe(false)
  })
})
