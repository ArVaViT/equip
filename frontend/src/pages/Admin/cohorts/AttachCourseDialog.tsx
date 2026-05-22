import { useEffect, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { Modal } from "@/components/patterns"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { cohortsService } from "@/services/cohorts"
import { coursesService } from "@/services/courses"
import { toast } from "@/lib/toast"
import type { Course } from "@/types"

interface Props {
  open: boolean
  onClose: () => void
  cohortId: string
  attachedCourseIds: string[]
  onAttached: () => void
}

/** Pick a course to attach. Already-attached courses are hidden. */
export function AttachCourseDialog({
  open,
  onClose,
  cohortId,
  attachedCourseIds,
  onAttached,
}: Props) {
  const { t } = useTranslation()
  const [courses, setCourses] = useState<Course[]>([])
  const [loading, setLoading] = useState(false)
  const [selected, setSelected] = useState("")
  const [saving, setSaving] = useState(false)

  // Stash the array in a ref so the effect's dep set is just ``open``
  // (a bool) and ``t``. Previously ``attachedCourseIds`` was in the
  // deps -- the parent passes ``cohort.course_ids`` which is a fresh
  // reference on every parent re-render, so any unrelated re-render
  // while this dialog is open would refire the effect, reload the
  // course catalog, and silently reset ``selected`` to the first
  // course -- discarding the admin's pick.
  const attachedRef = useRef(attachedCourseIds)
  useEffect(() => {
    attachedRef.current = attachedCourseIds
  }, [attachedCourseIds])

  useEffect(() => {
    if (!open) return
    let cancelled = false
    setLoading(true)
    coursesService
      .getCourses()
      .then((list) => {
        if (cancelled) return
        const available = list.filter((c) => !attachedRef.current.includes(c.id))
        setCourses(available)
        setSelected(available[0]?.id ?? "")
      })
      .catch(() => {
        if (!cancelled) toast({ title: t("admin.cohorts.toast.loadCoursesFailed"), variant: "destructive" })
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [open, t])

  const submit = async () => {
    // Guard against rapid double-clicks / Enter+click races -- without
    // this the same attach call fires twice and the second response
    // either 409s or quietly succeeds on the next render's stale
    // ``selected``. Toast on second response then reads "Failed"
    // though the first call succeeded.
    if (!selected || saving) return
    setSaving(true)
    try {
      await cohortsService.attachCourseToCohort(cohortId, selected)
      toast({ title: t("admin.cohorts.toast.courseAttached"), variant: "success" })
      onAttached()
    } catch {
      toast({ title: t("admin.cohorts.toast.attachFailed"), variant: "destructive" })
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal open={open} onClose={onClose} title={t("admin.cohorts.attachCourseTitle")}>
      <div className="space-y-4">
        {loading ? (
          <p className="text-sm text-muted-foreground py-4">{t("common.loading")}</p>
        ) : courses.length === 0 ? (
          <p className="text-sm text-muted-foreground py-4">
            {t("admin.cohorts.noMoreCourses")}
          </p>
        ) : (
          <div className="space-y-1.5">
            <Label className="text-xs">{t("admin.cohorts.pickCourse")}</Label>
            <Select value={selected} onValueChange={setSelected}>
              <SelectTrigger aria-label={t("admin.cohorts.pickCourse")}>
                <SelectValue placeholder={t("admin.cohorts.pickCourse")} />
              </SelectTrigger>
              <SelectContent>
                {courses.map((c) => (
                  <SelectItem key={c.id} value={c.id}>
                    {c.title} {c.status === "draft" ? `· ${t("admin.cohorts.draftTag")}` : ""}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        )}
        <div className="flex justify-end gap-2 pt-2">
          <Button variant="outline" onClick={onClose} disabled={saving}>
            {t("common.cancel")}
          </Button>
          <Button onClick={submit} disabled={!selected || saving || loading}>
            {saving ? t("admin.cohorts.attaching") : t("admin.cohorts.attach")}
          </Button>
        </div>
      </div>
    </Modal>
  )
}
