import { describe, it, expect, vi, beforeEach } from "vitest"

// The `course-materials` bucket's RLS policy (`course_materials_enrolled_read`)
// authorises a download by matching the object's FIRST path segment against
// the caller's enrolment / course ownership. So every upload into that bucket
// MUST be keyed `{courseId}/...` or enrolled students get a 400 when signing
// the file. These tests pin that invariant — a regression here was the exact
// bug that hid a chapter PDF from a real pilot student (block files were once
// stored under `{chapterId}/...`, which matches no course).
//
// `vi.hoisted` so the upload spy exists before the hoisted `vi.mock` factory
// runs; the mock only needs the storage surface the upload helpers touch.
const { uploadMock } = vi.hoisted(() => ({ uploadMock: vi.fn() }))

vi.mock("@/lib/supabase", () => ({
  supabase: {
    storage: {
      from: vi.fn(() => ({ upload: uploadMock })),
    },
  },
}))

import { storageService } from "@/services/storage"

const COURSE_ID = "1f3c4803-d229-464b-ad8e-848a0355e71f"
const CHAPTER_ID = "e7a8cfa0-e93a-4dfb-9648-ad6605a9ca2e"

function makeFile(name = "Lecture Notes.pdf"): File {
  return new File(["pdf-bytes"], name, { type: "application/pdf" })
}

describe("storageService course-materials path convention", () => {
  beforeEach(() => {
    uploadMock.mockReset()
    uploadMock.mockResolvedValue({ error: null })
  })

  it("uploadBlockFile keys the object under {courseId}/{chapterId}/", async () => {
    const { bucket, path } = await storageService.uploadBlockFile(COURSE_ID, CHAPTER_ID, makeFile())

    expect(bucket).toBe("course-materials")
    // RLS-critical: first segment is the course id, second the chapter id.
    expect(path.startsWith(`${COURSE_ID}/${CHAPTER_ID}/`)).toBe(true)
    expect(path.split("/")[0]).toBe(COURSE_ID)
    // The path the helper returns is exactly what it asked storage to store.
    expect(uploadMock).toHaveBeenCalledWith(path, expect.any(File))
  })

  it("uploadCourseMaterial keys the object under {courseId}/", async () => {
    await storageService.uploadCourseMaterial(COURSE_ID, makeFile())

    const storedPath = uploadMock.mock.calls[0]?.[0] as string
    expect(storedPath.split("/")[0]).toBe(COURSE_ID)
  })

  it("sanitises spaces/special chars in the file name segment", async () => {
    const { path } = await storageService.uploadBlockFile(COURSE_ID, CHAPTER_ID, makeFile('a b/c:d?.pdf'))
    const nameSegment = path.split("/").slice(2).join("/")
    expect(nameSegment).not.toMatch(/[ /\\:*?"<>|]/)
    expect(nameSegment.endsWith(".pdf")).toBe(true)
  })
})
