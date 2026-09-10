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
const { uploadMock, listMock, removeMock, fromMock } = vi.hoisted(() => {
  const uploadMock = vi.fn()
  const listMock = vi.fn()
  const removeMock = vi.fn()
  const fromMock = vi.fn(() => ({ upload: uploadMock, list: listMock, remove: removeMock }))
  return { uploadMock, listMock, removeMock, fromMock }
})

vi.mock("@/lib/supabase", () => ({
  supabase: {
    storage: {
      from: fromMock,
    },
  },
}))

import { parsePublicObjectUrl, storageService } from "@/services/storage"

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

  it("keeps the teacher's own file name for the block, Cyrillic and all", async () => {
    // The key is transliterated for Storage; the name the teacher sees on
    // the block is what they typed. Both are right, and they differ.
    const { path, name } = await storageService.uploadBlockFile(
      COURSE_ID,
      CHAPTER_ID,
      makeFile("Проповедь.pdf"),
    )
    expect(name).toBe("Проповедь.pdf")
    expect(path.endsWith("-Propoved.pdf")).toBe(true)
  })
})

/**
 * The bucket decides on the multipart part's Content-Type, and storage-js
 * takes that from the File — the `contentType` option is ignored for Blob
 * bodies. So a browser's spelling of a format has to be folded onto the
 * bucket's before the request, or an iPhone voice memo is a 415.
 */
describe("storageService content type", () => {
  beforeEach(() => {
    uploadMock.mockReset()
    uploadMock.mockResolvedValue({ error: null })
  })

  it("sends an m4a voice memo as audio/mp4, the name the bucket knows", async () => {
    const memo = new File(["aac-bytes"], "Заметка.m4a", { type: "audio/x-m4a" })
    await storageService.uploadCourseMaterial(COURSE_ID, memo)

    const sent = uploadMock.mock.calls[0]?.[1] as File
    expect(sent.type).toBe("audio/mp4")
    expect(sent.name).toBe("Заметка.m4a")
    expect(sent.size).toBe(memo.size)
  })

  it("types an untyped file by its extension", async () => {
    // Chrome on Windows hands over ``""`` for a file it has no association for.
    const pdf = new File(["%PDF"], "notes.pdf", { type: "" })
    await storageService.uploadCourseMaterial(COURSE_ID, pdf)
    expect((uploadMock.mock.calls[0]?.[1] as File).type).toBe("application/pdf")
  })

  it("passes a file the bucket already agrees with straight through", async () => {
    const pdf = makeFile()
    await storageService.uploadCourseMaterial(COURSE_ID, pdf)
    expect(uploadMock.mock.calls[0]?.[1]).toBe(pdf)
  })

  it("leaves a type the bucket cannot take alone, so the server's answer is honest", async () => {
    const video = new File(["mp4"], "clip.mp4", { type: "video/mp4" })
    await storageService.uploadCourseMaterial(COURSE_ID, video)
    expect(uploadMock.mock.calls[0]?.[1]).toBe(video)
  })
})

describe("storageService.listCourseMaterials", () => {
  beforeEach(() => {
    listMock.mockReset()
  })

  it("hides the chapter sub-folders Storage lists beside the files", async () => {
    // A chapter with a file block is a folder ``{courseId}/{chapterId}/``
    // inside the course prefix; ``list`` returns it as a row with
    // ``id: null`` and no metadata. It rendered as a material named after
    // the chapter's UUID that no one could download.
    listMock.mockResolvedValue({
      error: null,
      data: [
        {
          name: "1725580800000-Propoved.pdf",
          id: "b0f7c7b1-2f0b-4a2b-9c3f-0f1a2b3c4d5e",
          created_at: "2026-09-05T10:00:00Z",
          metadata: { size: 1234 },
        },
        { name: CHAPTER_ID, id: null, created_at: null, metadata: null },
      ],
    })

    const materials = await storageService.listCourseMaterials(COURSE_ID)

    expect(materials).toHaveLength(1)
    expect(materials[0]).toMatchObject({
      name: "1725580800000-Propoved.pdf",
      path: `${COURSE_ID}/1725580800000-Propoved.pdf`,
      size: 1234,
    })
  })
})

/**
 * Replacing a cover used to write the same object key with `upsert: true`,
 * and that did two wrong things at once.
 *
 * Storage looks up the existing object before an upsert, under RLS —
 * and migration 20260421010827 left `course-assets` and `avatars` with no
 * SELECT policy at all, so the lookup finds nothing and the write fails
 * as "new row violates row-level security policy". Confirmed on
 * production 2026-09-09: as `authenticated` carrying a teacher's claims,
 * `storage.objects` returns zero rows for `course-assets`.
 *
 * And a public bucket serves objects with an hour of `cache-control`, so
 * even a successful same-key replacement showed the teacher their old
 * picture long after the upload said it worked.
 */
describe("replacing a public image", () => {
  beforeEach(() => {
    uploadMock.mockReset()
    uploadMock.mockResolvedValue({ error: null })
    removeMock.mockReset()
    removeMock.mockResolvedValue({ error: null })
    fromMock.mockClear()
  })

  it("writes a cover under a fresh key, never upserting", async () => {
    const url = await storageService.uploadCourseImage(COURSE_ID, new File([""], "cover.png", { type: "image/png" }))

    const [path, , options] = uploadMock.mock.calls[0] ?? []
    expect(path).toMatch(new RegExp(`^${COURSE_ID}/cover-[0-9a-f]{8}\\.png$`))
    // No `{ upsert: true }` — that is the call that RLS refuses.
    expect(options).toBeUndefined()
    expect(url).toBe(`/img/course-assets/${path}`)
  })

  it("gives two uploads of the same file two different keys", async () => {
    const file = () => new File([""], "cover.png", { type: "image/png" })
    const first = await storageService.uploadCourseImage(COURSE_ID, file())
    const second = await storageService.uploadCourseImage(COURSE_ID, file())
    expect(first).not.toBe(second)
  })

  it("writes an avatar under a fresh key too", async () => {
    const userId = "109bc291-018d-4e43-8a7c-385a35bd6800"
    await storageService.uploadAvatar(userId, new File([""], "me.jpg", { type: "image/jpeg" }))

    const [path, , options] = uploadMock.mock.calls[0] ?? []
    expect(path).toMatch(new RegExp(`^${userId}/avatar-[0-9a-f]{8}\\.jpg$`))
    expect(options).toBeUndefined()
  })

  it("removes the object a stored URL points at", async () => {
    await storageService.removePublicObject(`/img/course-assets/${COURSE_ID}/cover-abcd1234.png`)

    expect(fromMock).toHaveBeenCalledWith("course-assets")
    expect(removeMock).toHaveBeenCalledWith([`${COURSE_ID}/cover-abcd1234.png`])
  })

  it("leaves anything it did not upload alone", async () => {
    for (const url of [null, undefined, "", "https://example.com/logo.png", "/img/course-assets"]) {
      await storageService.removePublicObject(url)
    }
    expect(removeMock).not.toHaveBeenCalled()
  })
})

describe("parsePublicObjectUrl", () => {
  it("reads the proxied form we store", () => {
    expect(parsePublicObjectUrl("/img/avatars/u1/avatar-1234abcd.png")).toEqual({
      bucket: "avatars",
      path: "u1/avatar-1234abcd.png",
    })
  })

  it("reads the raw Supabase form older rows hold", () => {
    expect(
      parsePublicObjectUrl(
        "https://rrisqutxlkamwfhcashl.supabase.co/storage/v1/object/public/course-assets/c1/cover.png",
      ),
    ).toEqual({ bucket: "course-assets", path: "c1/cover.png" })
  })

  it("keeps a nested key whole", () => {
    expect(parsePublicObjectUrl("/img/course-assets/content-images/1-ab.png")?.path).toBe(
      "content-images/1-ab.png",
    )
  })

  it("returns null for a URL from somewhere else", () => {
    expect(parsePublicObjectUrl("https://cdn.example.com/x.png")).toBeNull()
    expect(parsePublicObjectUrl("not a url at all")).toBeNull()
  })
})
