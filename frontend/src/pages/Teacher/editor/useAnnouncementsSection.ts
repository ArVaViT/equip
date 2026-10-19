import { useCallback, useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { coursesService } from "@/services/courses"
import { toast } from "@/lib/toast"
import type { Announcement } from "@/types"
import type { useConfirm } from "@/components/ui/alert-dialog"

type Confirm = ReturnType<typeof useConfirm>

interface AnnouncementsSection {
  announcements: Announcement[]
  /** The list could not be read — not the same as an empty list. */
  loadFailed: boolean
  reload: () => void
  title: string
  setTitle: (v: string) => void
  content: string
  setContent: (v: string) => void
  /** The announcement the form is editing, or ``null`` when it is composing a new one. */
  editingId: string | null
  /** True when the form holds something not yet posted: text typed into a
   *  blank form, or an edit that differs from the announcement it started
   *  from. What «close without saving?» is asked about. */
  dirty: boolean
  posting: boolean
  /** Create when nothing is being edited; save the edit otherwise. */
  post: () => Promise<void>
  startEdit: (a: Announcement) => void
  remove: (id: string) => Promise<void>
  resetForm: () => void
}

/**
 * Owns the "Announcements" modal state for a course: the list, the
 * inline form (compose or edit), and the post / save / delete handlers.
 */
export function useAnnouncementsSection(
  courseId: string | undefined,
  confirm: Confirm,
): AnnouncementsSection {
  const { t } = useTranslation()
  const [announcements, setAnnouncements] = useState<Announcement[]>([])
  const [title, setTitle] = useState("")
  const [content, setContent] = useState("")
  const [editingId, setEditingId] = useState<string | null>(null)
  const [posting, setPosting] = useState(false)
  // A list that could not be read must not look like an empty one: a
  // teacher who sees «No announcements yet» posts the notice again, and
  // every student is mailed twice.
  const [loadFailed, setLoadFailed] = useState(false)
  const [loadAttempt, setLoadAttempt] = useState(0)
  const reload = useCallback(() => setLoadAttempt((n) => n + 1), [])

  useEffect(() => {
    if (!courseId) return
    let cancelled = false
    setLoadFailed(false)
    coursesService
      .getAnnouncementsForEdit(courseId)
      .then((a) => {
        if (!cancelled) setAnnouncements(a)
      })
      .catch(() => {
        if (!cancelled) setLoadFailed(true)
      })
    return () => {
      cancelled = true
    }
  }, [courseId, loadAttempt])

  const resetForm = useCallback(() => {
    setTitle("")
    setContent("")
    setEditingId(null)
  }, [])

  const startEdit = useCallback((a: Announcement) => {
    setTitle(a.title)
    setContent(a.content)
    setEditingId(a.id)
  }, [])

  const post = useCallback(async () => {
    if (!courseId || !title.trim()) return
    setPosting(true)
    try {
      if (editingId) {
        const updated = await coursesService.updateAnnouncement(editingId, {
          title: title.trim(),
          // The API refuses an empty body (``min_length=1``) and the form
          // allows one, so an emptied body is simply not sent: the old
          // text stays, which is also what the teacher sees on the card.
          content: content.trim() || undefined,
        })
        setAnnouncements((p) => p.map((a) => (a.id === editingId ? updated : a)))
        toast({ title: t("teacherEditor.toast.announcementUpdated"), variant: "success" })
      } else {
        const a = await coursesService.createAnnouncement({
          title: title.trim(),
          content: content.trim(),
          course_id: courseId,
        })
        setAnnouncements((p) => [a, ...p])
        toast({ title: t("teacherEditor.toast.announcementPosted"), variant: "success" })
      }
      resetForm()
    } catch {
      toast({
        title: t(
          editingId
            ? "teacherEditor.toast.announcementUpdateFailed"
            : "teacherEditor.toast.announcementPostFailed",
        ),
        variant: "destructive",
      })
    } finally {
      setPosting(false)
    }
  }, [courseId, title, content, editingId, resetForm, t])

  const remove = useCallback(
    async (id: string) => {
      const ok = await confirm({
        title: t("teacherEditor.confirm.deleteAnnouncementTitle"),
        confirmLabel: t("teacherEditor.confirm.deleteAnnouncementAction"),
        tone: "destructive",
      })
      if (!ok) return
      try {
        await coursesService.deleteAnnouncement(id)
        setAnnouncements((p) => p.filter((a) => a.id !== id))
        if (editingId === id) resetForm()
      } catch {
        toast({ title: t("teacherEditor.toast.announcementDeleteFailed"), variant: "destructive" })
      }
    },
    [confirm, t, editingId, resetForm],
  )

  // Compared with the announcement as it stands, not with blank: an edit
  // opened and closed untouched has nothing to lose.
  const original = editingId ? announcements.find((a) => a.id === editingId) : undefined
  const dirty = original
    ? title !== original.title || content !== original.content
    : title.trim() !== "" || content.trim() !== ""

  return {
    announcements,
    loadFailed,
    reload,
    title,
    setTitle,
    content,
    setContent,
    editingId,
    dirty,
    posting,
    post,
    startEdit,
    remove,
    resetForm,
  }
}
