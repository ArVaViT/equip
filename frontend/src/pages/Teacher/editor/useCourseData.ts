import { useCallback, useEffect, useMemo, useState } from "react"
import { useTranslation } from "react-i18next"
import type { DropResult } from "@hello-pangea/dnd"
import { coursesService } from "@/services/courses"
import { storageService } from "@/services/storage"
import { toast } from "@/lib/toast"
import { isoToLocalInput, localInputToIso } from "@/i18n/format"
import type { Course } from "@/types"
import type { useConfirm } from "@/components/ui/alert-dialog"

type Confirm = ReturnType<typeof useConfirm>

type CoursePatch = Parameters<typeof coursesService.updateCourse>[1]

interface CourseData {
  course: Course | null
  loading: boolean
  sortedModules: NonNullable<Course["modules"]>
  /** True when the course status is "published". */
  published: boolean
  enrollStart: string
  setEnrollStart: (v: string) => void
  enrollEnd: string
  setEnrollEnd: (v: string) => void
  savingEnrollment: boolean
  savePatch: (patch: CoursePatch) => Promise<void>
  uploadCover: (file: File) => Promise<string>
  removeCover: () => Promise<void>
  saveEnrollment: () => Promise<boolean>
  togglePublish: () => Promise<void>
  addModule: () => Promise<void>
  removeModule: (id: string) => Promise<void>
  reorderModules: (result: DropResult) => Promise<void>
}

/**
 * Loads a course and exposes every mutation a teacher can make to the
 * course itself (title, description, cover, publish status, enrollment
 * window) and to its modules (create, delete, drag-to-reorder).
 *
 * The five modal concerns (announcements, materials, cohorts, events)
 * each have their own hook so the editor page stays a thin orchestrator.
 */
export function useCourseData(
  courseId: string | undefined,
  confirm: Confirm,
  onNotFound: () => void,
): CourseData {
  const { t } = useTranslation()
  const [course, setCourse] = useState<Course | null>(null)
  const [loading, setLoading] = useState(true)
  const [enrollStart, setEnrollStart] = useState("")
  const [enrollEnd, setEnrollEnd] = useState("")
  const [savingEnrollment, setSavingEnrollment] = useState(false)
  const [reordering, setReordering] = useState(false)

  const loadCourse = useCallback(
    async (signal: { cancelled: boolean }) => {
      if (!courseId) return
      setLoading(true)
      try {
        // `getCourseForEdit` forces ``?source=1`` so the InlineEdit fields
        // bind to the source-language `title` / `description` columns,
        // not the translation overlay. Without this an admin/owner in EN
        // UI would type into the EN translation and save it back over
        // the source.
        const data = await coursesService.getCourseForEdit(courseId)
        if (signal.cancelled) return
        setCourse(data)
        setEnrollStart(isoToLocalInput(data.enrollment_start))
        setEnrollEnd(isoToLocalInput(data.enrollment_end))
      } catch {
        if (!signal.cancelled) onNotFound()
      } finally {
        if (!signal.cancelled) setLoading(false)
      }
    },
    [courseId, onNotFound],
  )

  useEffect(() => {
    const signal = { cancelled: false }
    void loadCourse(signal)
    return () => {
      signal.cancelled = true
    }
  }, [loadCourse])

  const savePatch = useCallback(
    async (patch: CoursePatch) => {
      if (!courseId) return
      try {
        const updated = await coursesService.updateCourse(courseId, patch)
        setCourse((p) => (p ? { ...p, ...updated } : p))
        toast({ title: t("teacherEditor.toast.saved"), variant: "success" })
      } catch {
        toast({ title: t("teacherEditor.toast.saveFailed"), variant: "destructive" })
        throw new Error("save failed")
      }
    },
    [courseId, t],
  )

  const uploadCover = useCallback(
    async (file: File) => {
      if (!courseId) throw new Error("no course")
      const url = await storageService.uploadCourseImage(courseId, file)
      await coursesService.updateCourse(courseId, { image_url: url })
      setCourse((p) => (p ? { ...p, image_url: url } : p))
      toast({ title: t("teacherEditor.toast.coverUpdated"), variant: "success" })
      return url
    },
    [courseId, t],
  )

  const removeCover = useCallback(async () => {
    if (!courseId) return
    try {
      await coursesService.updateCourse(courseId, { image_url: null })
      setCourse((p) => (p ? { ...p, image_url: null } : p))
      toast({ title: t("teacherEditor.toast.coverRemoved"), variant: "success" })
    } catch {
      toast({ title: t("teacherEditor.toast.coverRemoveFailed"), variant: "destructive" })
    }
  }, [courseId, t])

  const saveEnrollment = useCallback(async () => {
    if (!courseId) return false
    setSavingEnrollment(true)
    try {
      const payload = {
        enrollment_start: localInputToIso(enrollStart),
        enrollment_end: localInputToIso(enrollEnd),
      }
      await coursesService.updateCourse(courseId, payload)
      setCourse((p) => (p ? { ...p, ...payload } : p))
      toast({ title: t("teacherEditor.toast.enrollmentSaved"), variant: "success" })
      return true
    } catch {
      toast({ title: t("teacherEditor.toast.saveFailed"), variant: "destructive" })
      return false
    } finally {
      setSavingEnrollment(false)
    }
  }, [courseId, enrollStart, enrollEnd, t])

  const togglePublish = useCallback(async () => {
    if (!courseId || !course) return
    const next = course.status === "published" ? ("draft" as const) : ("published" as const)
    try {
      await coursesService.updateCourse(courseId, { status: next })
      setCourse((p) => (p ? { ...p, status: next } : p))
      toast({
        title:
          next === "published"
            ? t("teacherEditor.toast.published")
            : t("teacherEditor.toast.unpublished"),
        variant: "success",
      })
    } catch {
      toast({ title: t("teacherEditor.toast.publishFailed"), variant: "destructive" })
    }
  }, [courseId, course, t])

  const addModule = useCallback(async () => {
    if (!courseId) return
    const order = course?.modules?.length ?? 0
    try {
      const m = await coursesService.createModule(courseId, {
        // Seed in the teacher's UI locale. The previous ``Module N``
        // literal was persisted as-is, so a Russian-UI teacher had to
        // rename every freshly-added module or live with an English
        // word in their course tree.
        title: t("teacherEditor.defaults.moduleTitle", { n: order + 1 }),
        order_index: order,
      })
      setCourse((p) =>
        p ? { ...p, modules: [...(p.modules ?? []), { ...m, chapters: [] }] } : p,
      )
      toast({ title: t("teacherEditor.toast.moduleAdded"), variant: "success" })
    } catch {
      toast({ title: t("teacherEditor.toast.moduleAddFailed"), variant: "destructive" })
    }
  }, [courseId, course?.modules?.length, t])

  const removeModule = useCallback(
    async (id: string) => {
      if (!courseId) return
      const ok = await confirm({
        title: t("teacherEditor.confirm.deleteModuleTitle"),
        description: t("teacherEditor.confirm.deleteModuleDescription"),
        confirmLabel: t("teacherEditor.confirm.deleteModuleAction"),
        tone: "destructive",
      })
      if (!ok) return
      try {
        await coursesService.deleteModule(courseId, id)
        setCourse((p) => (p ? { ...p, modules: p.modules?.filter((m) => m.id !== id) } : p))
      } catch {
        toast({ title: t("teacherEditor.toast.moduleRemoveFailed"), variant: "destructive" })
      }
    },
    [courseId, confirm, t],
  )

  const sortedModules = useMemo(
    () => [...(course?.modules ?? [])].sort((a, b) => a.order_index - b.order_index),
    [course?.modules],
  )

  const reorderModules = useCallback(
    async (result: DropResult) => {
      if (!result.destination || !courseId || reordering) return
      const from = result.source.index
      const to = result.destination.index
      if (from === to) return

      const reordered = Array.from(sortedModules)
      const [moved] = reordered.splice(from, 1)
      if (!moved) return
      reordered.splice(to, 0, moved)

      setCourse((prev) =>
        prev
          ? { ...prev, modules: reordered.map((m, i) => ({ ...m, order_index: i })) }
          : prev,
      )

      setReordering(true)
      try {
        await Promise.all(
          reordered
            .map((m, i) =>
              m.order_index !== i
                ? coursesService.updateModule(courseId, m.id, { order_index: i })
                : null,
            )
            .filter(Boolean),
        )
      } catch {
        toast({ title: t("teacherEditor.toast.moduleOrderFailed"), variant: "destructive" })
        void loadCourse({ cancelled: false })
      } finally {
        setReordering(false)
      }
    },
    [sortedModules, courseId, loadCourse, reordering, t],
  )

  return {
    course,
    loading,
    sortedModules,
    published: course?.status === "published",
    enrollStart,
    setEnrollStart,
    enrollEnd,
    setEnrollEnd,
    savingEnrollment,
    savePatch,
    uploadCover,
    removeCover,
    saveEnrollment,
    togglePublish,
    addModule,
    removeModule,
    reorderModules,
  }
}
