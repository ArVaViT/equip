import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { Modal } from "@/components/patterns"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import { NativeSelect } from "@/components/ui/native-select"
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

  useEffect(() => {
    if (!open) return
    let cancelled = false
    setLoading(true)
    coursesService
      .getCourses()
      .then((list) => {
        if (cancelled) return
        const available = list.filter((c) => !attachedCourseIds.includes(c.id))
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
  }, [open, attachedCourseIds, t])

  const submit = async () => {
    if (!selected) return
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
            <NativeSelect value={selected} onChange={(e) => setSelected(e.target.value)}>
              {courses.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.title} {c.status === "draft" ? `· ${t("admin.cohorts.draftTag")}` : ""}
                </option>
              ))}
            </NativeSelect>
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
