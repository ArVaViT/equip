import { normalizeChapterType } from "@/lib/chapterTypes"
import type { Chapter, ChapterBlock, Course, Module } from "@/types"

const DATABASE_NAME = "equip-offline-learning"
const DATABASE_VERSION = 1
const STORE_NAME = "courses"

interface OfflineCourseRecord {
  key: string
  userId: string
  locale: string
  courseId: string
  course: Course
  lessons: Record<string, ChapterBlock[]>
  updatedAt: number
}

export interface OfflineLessonSnapshot {
  course: Course
  blocks: ChapterBlock[]
}

let databasePromise: Promise<IDBDatabase> | null = null

function openDatabase(): Promise<IDBDatabase> {
  if (typeof indexedDB === "undefined") {
    return Promise.reject(new Error("IndexedDB is unavailable"))
  }
  if (databasePromise) return databasePromise

  const opening = new Promise<IDBDatabase>((resolve, reject) => {
    const request = indexedDB.open(DATABASE_NAME, DATABASE_VERSION)
    request.onupgradeneeded = () => {
      request.result.createObjectStore(STORE_NAME, { keyPath: "key" })
    }
    request.onsuccess = () => {
      const database = request.result
      database.onversionchange = () => {
        database.close()
        databasePromise = null
      }
      resolve(database)
    }
    request.onerror = () => reject(request.error ?? new Error("Could not open offline lesson storage"))
    request.onblocked = () => reject(new Error("Offline lesson storage upgrade was blocked"))
  }).catch((error: unknown) => {
    databasePromise = null
    throw error
  })

  databasePromise = opening
  return opening
}

function courseKey(userId: string, locale: string, courseId: string): string {
  return JSON.stringify([userId, locale, courseId])
}

function chapterOf(course: Course, chapterId: string): Chapter | undefined {
  for (const chapter of course.chapters ?? []) {
    if (chapter.id === chapterId) return chapter
  }
  for (const module of course.modules ?? []) {
    const chapter = module.chapters?.find((item) => item.id === chapterId)
    if (chapter) return chapter
  }
  return undefined
}

function liveReadingChapterIds(course: Course): Set<string> {
  const ids = new Set<string>()
  for (const chapter of course.chapters ?? []) {
    if (!chapter.deleted_at && normalizeChapterType(chapter.chapter_type) === "reading") {
      ids.add(chapter.id)
    }
  }
  for (const module of course.modules ?? []) {
    if (module.deleted_at) continue
    for (const chapter of module.chapters ?? []) {
      if (!chapter.deleted_at && normalizeChapterType(chapter.chapter_type) === "reading") {
        ids.add(chapter.id)
      }
    }
  }
  return ids
}

function safeChapter(chapter: Chapter): Chapter {
  return {
    id: chapter.id,
    course_id: chapter.course_id,
    module_id: chapter.module_id,
    title: chapter.title,
    order_index: chapter.order_index,
    chapter_type: chapter.chapter_type,
    requires_completion: chapter.requires_completion,
    is_locked: chapter.is_locked,
    deleted_at: null,
  }
}

function safeCourse(course: Course, cachedLessonIds: Set<string>): Course {
  const chapters = (course.chapters ?? [])
    .filter((chapter) => cachedLessonIds.has(chapter.id) && !chapter.deleted_at)
    .map(safeChapter)
  const modules: Module[] = (course.modules ?? [])
    .filter((module) => !module.deleted_at)
    .map((module) => ({
      id: module.id,
      course_id: module.course_id,
      title: module.title,
      description: null,
      order_index: module.order_index,
      due_date: null,
      chapters: (module.chapters ?? [])
        .filter((chapter) => cachedLessonIds.has(chapter.id) && !chapter.deleted_at)
        .map(safeChapter),
    }))
    .filter((module) => (module.chapters?.length ?? 0) > 0)

  return {
    id: course.id,
    title: course.title,
    description: course.description,
    image_url: null,
    status: "published",
    access_mode: course.access_mode,
    created_at: course.created_at,
    updated_at: course.updated_at,
    deleted_at: null,
    enrollment_start: null,
    enrollment_end: null,
    modules,
    chapters,
    chapter_count: cachedLessonIds.size,
    module_count: modules.length,
  }
}

function safeTextBlocks(blocks: ChapterBlock[], chapterId: string): ChapterBlock[] {
  return blocks
    .filter((block) => block.block_type === "text" && block.chapter_id === chapterId)
    .map((block) => ({
      id: block.id,
      chapter_id: chapterId,
      block_type: "text",
      order_index: block.order_index,
      content: block.content,
      quiz_id: null,
      assignment_id: null,
      file_bucket: null,
      file_path: null,
      file_name: null,
    }))
}

function requestWithStore<T>(
  mode: IDBTransactionMode,
  start: (store: IDBObjectStore, transaction: IDBTransaction) => IDBRequest<T>,
): Promise<T> {
  return openDatabase().then(
    (database) =>
      new Promise<T>((resolve, reject) => {
        const transaction = database.transaction(STORE_NAME, mode)
        let value!: T
        let request: IDBRequest<T>
        try {
          request = start(transaction.objectStore(STORE_NAME), transaction)
        } catch (error) {
          transaction.abort()
          reject(error)
          return
        }
        request.addEventListener("success", () => {
          value = request.result
        })
        request.addEventListener("error", () => reject(request.error ?? new Error("Offline lesson request failed")))
        transaction.oncomplete = () => resolve(value)
        transaction.onerror = () => reject(transaction.error ?? new Error("Offline lesson transaction failed"))
        transaction.onabort = () => reject(transaction.error ?? new Error("Offline lesson transaction was aborted"))
      }),
  )
}

export async function saveOfflineLesson(
  userId: string,
  locale: string,
  course: Course,
  chapterId: string,
  blocks: ChapterBlock[],
): Promise<boolean> {
  const chapter = chapterOf(course, chapterId)
  if (
    !userId ||
    !locale ||
    course.status !== "published" ||
    course.deleted_at ||
    !chapter ||
    chapter.deleted_at ||
    normalizeChapterType(chapter.chapter_type) !== "reading"
  ) {
    return false
  }

  const content = safeTextBlocks(blocks, chapterId)
  const key = courseKey(userId, locale, course.id)
  await requestWithStore<IDBValidKey>("readwrite", (store) => {
    const request = store.get(key)
    request.onsuccess = () => {
      const existing = request.result as OfflineCourseRecord | undefined
      const allowedIds = liveReadingChapterIds(course)
      const lessons: Record<string, ChapterBlock[]> = {}
      for (const [id, savedBlocks] of Object.entries(existing?.lessons ?? {})) {
        if (allowedIds.has(id)) lessons[id] = savedBlocks
      }
      lessons[chapterId] = content
      const cachedLessonIds = new Set(Object.keys(lessons))
      const record: OfflineCourseRecord = {
        key,
        userId,
        locale,
        courseId: course.id,
        course: safeCourse(course, cachedLessonIds),
        lessons,
        updatedAt: Date.now(),
      }
      store.put(record)
    }
    return request
  })
  return true
}

export async function getOfflineLesson(
  userId: string,
  locale: string,
  courseId: string,
  chapterId: string,
): Promise<OfflineLessonSnapshot | null> {
  if (!userId || !locale) return null
  const record = await requestWithStore<OfflineCourseRecord | undefined>(
    "readonly",
    (store) => store.get(courseKey(userId, locale, courseId)),
  )
  const blocks = record?.lessons[chapterId]
  if (!record || !blocks) return null
  return { course: record.course, blocks }
}

async function updateRecords(
  update: (record: OfflineCourseRecord) => OfflineCourseRecord | null,
): Promise<void> {
  await requestWithStore<OfflineCourseRecord[]>("readwrite", (store) => {
    const request = store.getAll()
    request.onsuccess = () => {
      for (const record of request.result as OfflineCourseRecord[]) {
        const next = update(record)
        if (next) store.put(next)
        else store.delete(record.key)
      }
    }
    return request
  })
}

export function invalidateOfflineCourse(courseId: string): Promise<void> {
  return updateRecords((record) => (record.courseId === courseId ? null : record))
}

export function invalidateOfflineUserCourse(
  userId: string,
  courseId: string,
): Promise<void> {
  return updateRecords((record) =>
    record.userId === userId && record.courseId === courseId
      ? null
      : record,
  )
}

export function invalidateOfflineLesson(
  userId: string,
  courseId: string,
  chapterId: string,
): Promise<void> {
  return updateRecords((record) => {
    if (record.userId !== userId || record.courseId !== courseId) return record
    const lessons = { ...record.lessons }
    delete lessons[chapterId]
    if (Object.keys(lessons).length === 0) return null
    const cachedLessonIds = new Set(Object.keys(lessons))
    return {
      ...record,
      lessons,
      course: safeCourse(record.course, cachedLessonIds),
      updatedAt: Date.now(),
    }
  })
}

export function invalidateOfflineChapter(chapterId: string): Promise<void> {
  return updateRecords((record) => {
    if (!record.lessons[chapterId]) return record
    const lessons = { ...record.lessons }
    delete lessons[chapterId]
    if (Object.keys(lessons).length === 0) return null
    const cachedLessonIds = new Set(Object.keys(lessons))
    return {
      ...record,
      lessons,
      course: safeCourse(record.course, cachedLessonIds),
      updatedAt: Date.now(),
    }
  })
}

export function invalidateOfflineBlock(blockId: string): Promise<void> {
  return updateRecords((record) => {
    const chapterId = Object.entries(record.lessons).find(([, blocks]) =>
      blocks.some((block) => block.id === blockId),
    )?.[0]
    if (!chapterId) return record
    const lessons = { ...record.lessons }
    delete lessons[chapterId]
    if (Object.keys(lessons).length === 0) return null
    const cachedLessonIds = new Set(Object.keys(lessons))
    return {
      ...record,
      lessons,
      course: safeCourse(record.course, cachedLessonIds),
      updatedAt: Date.now(),
    }
  })
}
