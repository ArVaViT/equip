import { describe, expect, it, vi } from "vitest"
import type { Chapter, ChapterBlock, Course } from "@/types"

class FakeRequest<T> {
  result!: T
  onsuccess: ((event: Event) => void) | null = null
  onerror: ((event: Event) => void) | null = null
  onupgradeneeded: ((event: Event) => void) | null = null
  private readonly successListeners: Array<(event: Event) => void> = []
  private readonly errorListeners: Array<(event: Event) => void> = []

  addEventListener(type: string, listener: (event: Event) => void) {
    if (type === "success") this.successListeners.push(listener)
    if (type === "error") this.errorListeners.push(listener)
  }

  succeed(result: T) {
    this.result = result
    const event = new Event("success")
    this.onsuccess?.(event)
    for (const listener of this.successListeners) listener(event)
  }
}

class FakeTransaction {
  oncomplete: ((event: Event) => void) | null = null
  onerror: ((event: Event) => void) | null = null
  onabort: ((event: Event) => void) | null = null
  private pending = 0
  private scheduled = false

  constructor(private readonly records: Map<string, Record<string, unknown>>) {}

  objectStore() {
    return {
      get: (key: string) => this.schedule(() => this.records.get(key)),
      getAll: () => this.schedule(() => [...this.records.values()]),
      put: (record: { key: string }) =>
        this.schedule(() => {
          this.records.set(record.key, record)
          return record.key
        }),
      delete: (key: string) =>
        this.schedule(() => {
          this.records.delete(key)
          return undefined
        }),
    }
  }

  abort() {
    this.onabort?.(new Event("abort"))
  }

  private schedule<T>(action: () => T): FakeRequest<T> {
    const request = new FakeRequest<T>()
    this.pending += 1
    queueMicrotask(() => {
      request.succeed(action())
      this.pending -= 1
      this.finishIfReady()
    })
    return request
  }

  private finishIfReady() {
    if (this.pending !== 0 || this.scheduled) return
    this.scheduled = true
    queueMicrotask(() => {
      if (this.pending === 0) this.oncomplete?.(new Event("complete"))
      else this.scheduled = false
    })
  }
}

class FakeDatabase {
  onversionchange: (() => void) | null = null
  private readonly records = new Map<string, Record<string, unknown>>()

  createObjectStore() {
    return {}
  }

  transaction() {
    return new FakeTransaction(this.records)
  }
}

class FakeIndexedDB {
  private database: FakeDatabase | null = null

  open() {
    const request = new FakeRequest<FakeDatabase>()
    queueMicrotask(() => {
      if (!this.database) {
        this.database = new FakeDatabase()
        request.result = this.database
        request.onupgradeneeded?.(new Event("upgradeneeded") as unknown as Event)
      }
      request.succeed(this.database)
    })
    return request
  }
}

vi.stubGlobal("indexedDB", new FakeIndexedDB())

const {
  getOfflineLesson,
  invalidateOfflineBlock,
  invalidateOfflineChapter,
  invalidateOfflineCourse,
  invalidateOfflineLesson,
  invalidateOfflineUserCourse,
  saveOfflineLesson,
} =
  await import("@/lib/offlineLessons")

function makeChapter(id: string, type: Chapter["chapter_type"], order_index = 0): Chapter {
  return {
    id,
    course_id: "course-1",
    module_id: null,
    title: `Lesson ${id}`,
    order_index,
    chapter_type: type,
    requires_completion: false,
    is_locked: false,
  }
}

function makeCourse(chapters: Chapter[], status: Course["status"] = "published"): Course {
  return {
    id: "course-1",
    title: "Published course",
    description: "Public description",
    image_url: "/img/course-assets/course-1/cover.png",
    status,
    access_mode: "public",
    created_by: "teacher-private-id",
    viewer_can_edit: true,
    preview_chapter_id: "lesson-1",
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-02T00:00:00Z",
    deleted_at: null,
    enrollment_start: null,
    enrollment_end: null,
    modules: [],
    chapters,
  }
}

function makeBlock(id: string, chapterId: string, block_type: ChapterBlock["block_type"]): ChapterBlock {
  return {
    id,
    chapter_id: chapterId,
    block_type,
    order_index: 0,
    content: block_type === "text" ? `<p>${id}</p>` : null,
    quiz_id: block_type === "quiz" ? "private-quiz-id" : null,
    assignment_id: block_type === "assignment" ? "private-assignment-id" : null,
    file_bucket: block_type === "file" ? "private-bucket" : null,
    file_path: block_type === "file" ? "private/path.pdf" : null,
    file_name: block_type === "file" ? "secret.pdf" : null,
  }
}

describe("offline lesson storage", () => {
  const locale = "en"

  it("keeps only published reading text and isolates records by account", async () => {
    const course = makeCourse([
      makeChapter("lesson-1", "reading"),
      makeChapter("quiz-1", "quiz", 1),
    ])
    const blocks = [
      makeBlock("text-1", "lesson-1", "text"),
      makeBlock("quiz-block", "lesson-1", "quiz"),
      makeBlock("file-block", "lesson-1", "file"),
    ]

    await expect(saveOfflineLesson("account-a", locale, course, "lesson-1", blocks)).resolves.toBe(true)
    const accountA = await getOfflineLesson("account-a", locale, "course-1", "lesson-1")

    expect(accountA?.blocks).toHaveLength(1)
    expect(accountA?.blocks[0]).toMatchObject({
      block_type: "text",
      content: "<p>text-1</p>",
      quiz_id: null,
      assignment_id: null,
      file_path: null,
      file_name: null,
    })
    expect(accountA?.course.chapters?.map((chapter) => chapter.id)).toEqual(["lesson-1"])
    expect(accountA?.course).not.toHaveProperty("created_by")
    expect(accountA?.course).not.toHaveProperty("viewer_can_edit")
    expect(accountA?.course).not.toHaveProperty("preview_chapter_id")
    await expect(getOfflineLesson("account-b", locale, "course-1", "lesson-1")).resolves.toBeNull()
    await expect(getOfflineLesson("", locale, "course-1", "lesson-1")).resolves.toBeNull()
  })

  it("does not save drafts or non-reading lessons", async () => {
    const draft = makeCourse([makeChapter("lesson-1", "reading")], "draft")
    const quiz = makeCourse([makeChapter("quiz-1", "quiz")])

    await expect(saveOfflineLesson("account-c", locale, draft, "lesson-1", [])).resolves.toBe(false)
    await expect(saveOfflineLesson("account-c", locale, quiz, "quiz-1", [])).resolves.toBe(false)
    await expect(getOfflineLesson("account-c", locale, "course-1", "lesson-1")).resolves.toBeNull()
  })

  it("invalidates deleted blocks and stale chapters without affecting another account", async () => {
    const course = makeCourse([
      makeChapter("lesson-1", "reading"),
      makeChapter("lesson-2", "reading", 1),
    ])
    await saveOfflineLesson("account-d", locale, course, "lesson-1", [makeBlock("text-1", "lesson-1", "text")])
    await saveOfflineLesson("account-d", locale, course, "lesson-2", [makeBlock("text-2", "lesson-2", "text")])
    await saveOfflineLesson("account-e", locale, course, "lesson-1", [makeBlock("text-1", "lesson-1", "text")])

    await invalidateOfflineBlock("text-1")
    await expect(getOfflineLesson("account-d", locale, "course-1", "lesson-1")).resolves.toBeNull()
    await expect(getOfflineLesson("account-e", locale, "course-1", "lesson-1")).resolves.toBeNull()
    await expect(getOfflineLesson("account-d", locale, "course-1", "lesson-2")).resolves.toMatchObject({
      blocks: [{ id: "text-2" }],
    })

    await invalidateOfflineChapter("lesson-2")
    await expect(getOfflineLesson("account-d", locale, "course-1", "lesson-2")).resolves.toBeNull()
  })

  it("invalidates inaccessible lesson copies across locales only for that account", async () => {
    const course = makeCourse([
      makeChapter("lesson-1", "reading"),
      makeChapter("lesson-2", "reading", 1),
    ])
    await saveOfflineLesson("account-f", "en", course, "lesson-1", [makeBlock("text-en", "lesson-1", "text")])
    await saveOfflineLesson("account-f", "ru", course, "lesson-1", [makeBlock("text-ru", "lesson-1", "text")])
    await saveOfflineLesson("account-f", "en", course, "lesson-2", [makeBlock("text-next", "lesson-2", "text")])
    await saveOfflineLesson("account-g", "en", course, "lesson-1", [makeBlock("text-other", "lesson-1", "text")])

    await invalidateOfflineLesson("account-f", "course-1", "lesson-1")

    await expect(getOfflineLesson("account-f", "en", "course-1", "lesson-1")).resolves.toBeNull()
    await expect(getOfflineLesson("account-f", "ru", "course-1", "lesson-1")).resolves.toBeNull()
    await expect(getOfflineLesson("account-f", "en", "course-1", "lesson-2")).resolves.not.toBeNull()
    await expect(getOfflineLesson("account-g", "en", "course-1", "lesson-1")).resolves.not.toBeNull()
  })

  it("retains each account's copy across logout and clears only the requested account/course", async () => {
    const course = makeCourse([makeChapter("lesson-1", "reading")])
    const block = [makeBlock("text-retained", "lesson-1", "text")]
    await saveOfflineLesson("account-a", locale, course, "lesson-1", block)
    await saveOfflineLesson("account-a", "ru", course, "lesson-1", block)
    await saveOfflineLesson("account-b", locale, course, "lesson-1", block)

    await expect(getOfflineLesson("", locale, "course-1", "lesson-1")).resolves.toBeNull()
    await expect(getOfflineLesson("account-a", locale, "course-1", "lesson-1")).resolves.not.toBeNull()
    await expect(getOfflineLesson("account-b", locale, "course-1", "lesson-1")).resolves.not.toBeNull()

    await invalidateOfflineUserCourse("account-a", "course-1")
    await expect(getOfflineLesson("account-a", locale, "course-1", "lesson-1")).resolves.toBeNull()
    await expect(getOfflineLesson("account-a", "ru", "course-1", "lesson-1")).resolves.toBeNull()
    await expect(getOfflineLesson("account-b", locale, "course-1", "lesson-1")).resolves.not.toBeNull()

    await invalidateOfflineCourse("course-1")
    await expect(getOfflineLesson("account-b", locale, "course-1", "lesson-1")).resolves.toBeNull()
  })
})
