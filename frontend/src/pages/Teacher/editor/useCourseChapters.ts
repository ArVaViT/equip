import { useCallback, useRef, type Dispatch, type SetStateAction } from "react"
import { useNavigate } from "react-router-dom"
import { useTranslation } from "react-i18next"
import type { DropResult } from "@hello-pangea/dnd"

import { coursesService } from "@/services/courses"
import { toast } from "@/lib/toast"
import { getErrorDetail } from "@/lib/errorDetail"
import { makeChapterSchema } from "@/lib/validations/course"
import { chapterEditHref, readCourseStructure } from "@/lib/courseStructure"
import type { ChapterType } from "@/lib/chapterTypes"
import type { Chapter, Course } from "@/types"
import type { useConfirm } from "@/components/ui/alert-dialog"

type Confirm = ReturnType<typeof useConfirm>

interface Args {
  courseId: string | undefined
  course: Course | null
  setCourse: Dispatch<SetStateAction<Course | null>>
  confirm: Confirm
}

export interface CourseChapters {
  /** Write a lesson straight into the course and open it. */
  addChapter: (type: ChapterType) => Promise<void>
  /** Local-only, for the row's controlled input between keystrokes. */
  updateChapterLocal: (chapterId: string, patch: Partial<Chapter>) => void
  renameChapter: (chapter: Chapter, title: string) => Promise<void>
  toggleChapterLock: (chapter: Chapter) => Promise<void>
  deleteChapter: (chapterId: string) => Promise<void>
  /** `null` takes the lesson out of its module; an id files it under one. */
  moveChapter: (chapterId: string, moduleId: string | null) => Promise<void>
  reorderChapters: (result: DropResult) => Promise<void>
}

/**
 * Everything a teacher can do to a lesson from the course editor.
 *
 * The course editor could only ever reach a lesson through a module, so
 * this is new ground rather than a move: a lesson belongs to the course,
 * and the course is where it can now be written, renamed, reordered,
 * locked, filed under a module, and deleted.
 *
 * Split out of `useCourseData` so that file stays about the course itself.
 * It takes `course` / `setCourse` rather than owning them because the two
 * halves edit one payload — a lesson added here has to appear in the same
 * `course` the outline renders.
 *
 * Every call goes through the course-shaped chapter routes
 * (`createCourseChapter` and friends), which is what makes an ungrouped
 * lesson addressable at all.
 */
export function useCourseChapters({
  courseId,
  course,
  setCourse,
  confirm,
}: Args): CourseChapters {
  const navigate = useNavigate()
  const { t } = useTranslation()

  /** Patch a lesson wherever it lives — loose, or inside a module. */
  const updateChapterLocal = useCallback(
    (chapterId: string, patch: Partial<Chapter>) => {
      setCourse((prev) => {
        if (!prev) return prev
        const apply = (list: Chapter[] | undefined) =>
          list?.map((c) => (c.id === chapterId ? { ...c, ...patch } : c))
        return {
          ...prev,
          chapters: apply(prev.chapters),
          modules: prev.modules?.map((m) => ({ ...m, chapters: apply(m.chapters) })),
        }
      })
    },
    [setCourse],
  )

  const addingRef = useRef(false)
  const addChapter = useCallback(
    async (type: ChapterType) => {
      if (!courseId) return
      // Same guard as `addModule`: a second click before the optimistic
      // state lands would otherwise seed the same default title twice.
      if (addingRef.current) return
      addingRef.current = true
      // Numbered across the whole course, not one module's worth. The
      // module-scoped count is what made a teacher's second lesson open
      // as "Lesson 1" once the course had two modules.
      const all = readCourseStructure(course).chapters
      const sameType = all.filter((c) => c.chapter_type === type).length
      const typeKey = `lessons.defaults.${type}Title`
      const seeded = t(typeKey, { n: sameType + 1 })
      const title = seeded === typeKey ? t("lessons.defaults.chapterTitle", { n: all.length + 1 }) : seeded
      try {
        // No `order_index`: the server appends at the course's tail, which
        // is both what "add a lesson" means and immune to the stale-length
        // race a computed index would carry.
        const ch = await coursesService.createCourseChapter(courseId, {
          title,
          chapter_type: type,
        })
        setCourse((prev) =>
          prev ? { ...prev, chapters: [...(prev.chapters ?? []), ch] } : prev,
        )
        toast({ title: t("lessons.toast.added"), variant: "success" })
        navigate(chapterEditHref(courseId, ch.id))
      } catch {
        toast({ title: t("lessons.toast.addFailed"), variant: "destructive" })
      } finally {
        addingRef.current = false
      }
    },
    [course, courseId, navigate, setCourse, t],
  )

  const renameChapter = useCallback(
    async (chapter: Chapter, newTitle: string) => {
      if (!courseId || !newTitle.trim()) return
      const trimmed = newTitle.trim()
      const check = makeChapterSchema().pick({ title: true }).safeParse({ title: trimmed })
      if (!check.success) {
        toast({
          title: check.error.issues[0]?.message ?? t("lessons.invalidTitle"),
          variant: "destructive",
        })
        return
      }
      const previous = chapter.title
      updateChapterLocal(chapter.id, { title: trimmed })
      try {
        await coursesService.updateCourseChapter(courseId, chapter.id, { title: trimmed })
      } catch {
        updateChapterLocal(chapter.id, { title: previous })
        toast({ title: t("lessons.toast.renameFailed"), variant: "destructive" })
      }
    },
    [courseId, t, updateChapterLocal],
  )

  const toggleChapterLock = useCallback(
    async (chapter: Chapter) => {
      if (!courseId) return
      const locked = !chapter.is_locked
      updateChapterLocal(chapter.id, { is_locked: locked })
      try {
        await coursesService.updateCourseChapter(courseId, chapter.id, { is_locked: locked })
        toast({
          title: locked ? t("lessons.toast.locked") : t("lessons.toast.unlocked"),
          variant: "success",
        })
      } catch (error: unknown) {
        updateChapterLocal(chapter.id, { is_locked: chapter.is_locked })
        const detail = getErrorDetail(error) || t("lessons.unknownError")
        toast({ title: t("lessons.toast.lockFailed", { detail }), variant: "destructive" })
      }
    },
    [courseId, t, updateChapterLocal],
  )

  const deleteChapter = useCallback(
    async (chapterId: string) => {
      if (!courseId) return
      const ok = await confirm({
        title: t("lessons.confirmDelete.title"),
        description: t("lessons.confirmDelete.description"),
        confirmLabel: t("lessons.confirmDelete.confirm"),
        tone: "destructive",
      })
      if (!ok) return
      try {
        await coursesService.deleteCourseChapter(courseId, chapterId)
        setCourse((prev) =>
          prev ? { ...prev, chapters: prev.chapters?.filter((c) => c.id !== chapterId) } : prev,
        )
        toast({ title: t("lessons.toast.deleted"), variant: "success" })
      } catch {
        toast({ title: t("lessons.toast.deleteFailed"), variant: "destructive" })
      }
    },
    [confirm, courseId, setCourse, t],
  )

  const moveChapter = useCallback(
    async (chapterId: string, moduleId: string | null) => {
      if (!courseId) return
      try {
        // The server re-seats a regrouped lesson at the tail of its new
        // group and hands the row back, so the response — not the request
        // — is what local state must believe about `order_index`.
        const moved = await coursesService.updateCourseChapter(courseId, chapterId, {
          module_id: moduleId,
        })
        setCourse((prev) => {
          if (!prev) return prev
          const without = (list: Chapter[] | undefined) =>
            (list ?? []).filter((c) => c.id !== chapterId)
          return {
            ...prev,
            chapters: moduleId === null ? [...without(prev.chapters), moved] : without(prev.chapters),
            modules: prev.modules?.map((m) =>
              m.id === moduleId
                ? { ...m, chapters: [...without(m.chapters), moved] }
                : { ...m, chapters: without(m.chapters) },
            ),
          }
        })
        const target = moduleId
          ? (course?.modules ?? []).find((m) => m.id === moduleId)
          : null
        toast({
          title: target
            ? t("lessons.toast.movedToModule", { title: target.title })
            : t("lessons.toast.movedToCourse"),
          variant: "success",
        })
      } catch {
        toast({ title: t("lessons.toast.moveFailed"), variant: "destructive" })
      }
    },
    [course?.modules, courseId, setCourse, t],
  )

  const reorderingRef = useRef(false)
  const reorderChapters = useCallback(
    async (result: DropResult) => {
      if (!result.destination || !courseId || reorderingRef.current) return
      const from = result.source.index
      const to = result.destination.index
      if (from === to) return

      const sorted = [...(course?.chapters ?? [])].sort((a, b) => a.order_index - b.order_index)
      const reordered = Array.from(sorted)
      const [moved] = reordered.splice(from, 1)
      if (!moved) return
      reordered.splice(to, 0, moved)

      const renumbered = reordered.map((c, i) => ({ ...c, order_index: i }))
      setCourse((prev) => (prev ? { ...prev, chapters: renumbered } : prev))

      reorderingRef.current = true
      try {
        // Compare against the index the row is *stored* with, not against
        // where it used to sit in the list. Loose lessons share one course-
        // global order space with the grouped ones, so their indices are
        // rarely 0..n-1 to begin with — a positional check would skip rows
        // whose place did not move but whose number still has to.
        await Promise.all(
          reordered
            .map((c, i) =>
              c.order_index !== i
                ? coursesService.updateCourseChapter(courseId, c.id, { order_index: i })
                : null,
            )
            .filter(Boolean),
        )
      } catch {
        toast({ title: t("lessons.toast.reorderFailed"), variant: "destructive" })
        setCourse((prev) => (prev ? { ...prev, chapters: sorted } : prev))
      } finally {
        reorderingRef.current = false
      }
    },
    [course?.chapters, courseId, setCourse, t],
  )

  return {
    addChapter,
    updateChapterLocal,
    renameChapter,
    toggleChapterLock,
    deleteChapter,
    moveChapter,
    reorderChapters,
  }
}
