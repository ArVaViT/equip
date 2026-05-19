import { useState } from "react"
import { useTranslation } from "react-i18next"
import { Modal } from "@/components/patterns"
import { Button } from "@/components/ui/button"
import { DateTimePicker } from "@/components/ui/datetime-picker"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { cohortsService } from "@/services/cohorts"
import { toast } from "@/lib/toast"
import { localInputToIso } from "@/i18n/format"

interface Props {
  open: boolean
  onClose: () => void
  onCreated: () => void
}

/** Create-cohort form. Cohort starts empty; courses and students are
 *  attached separately on the detail page. */
export function CreateCohortDialog({ open, onClose, onCreated }: Props) {
  const { t } = useTranslation()
  const [name, setName] = useState("")
  const [start, setStart] = useState("")
  const [end, setEnd] = useState("")
  const [enrollStart, setEnrollStart] = useState("")
  const [enrollEnd, setEnrollEnd] = useState("")
  const [maxStudents, setMaxStudents] = useState("")
  const [saving, setSaving] = useState(false)

  const reset = () => {
    setName("")
    setStart("")
    setEnd("")
    setEnrollStart("")
    setEnrollEnd("")
    setMaxStudents("")
  }

  const handleClose = () => {
    if (saving) return
    reset()
    onClose()
  }

  const isValid =
    name.trim().length > 0 &&
    start &&
    end &&
    new Date(start).getTime() < new Date(end).getTime()

  const submit = async () => {
    if (!isValid) return
    setSaving(true)
    try {
      const startIso = localInputToIso(start)
      const endIso = localInputToIso(end)
      if (!startIso || !endIso) {
        setSaving(false)
        return
      }
      await cohortsService.createCohort({
        name: name.trim(),
        start_date: startIso,
        end_date: endIso,
        enrollment_start: localInputToIso(enrollStart),
        enrollment_end: localInputToIso(enrollEnd),
        max_students: maxStudents ? Number(maxStudents) : null,
      })
      toast({ title: t("admin.cohorts.toast.created"), variant: "success" })
      reset()
      onCreated()
    } catch {
      toast({ title: t("admin.cohorts.toast.createFailed"), variant: "destructive" })
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal open={open} onClose={handleClose} title={t("admin.cohorts.createTitle")}>
      <div className="space-y-4">
        <div className="space-y-1.5">
          <Label className="text-xs">{t("admin.cohorts.fieldName")}</Label>
          <Input
            value={name}
            onChange={(e) => setName(e.target.value.slice(0, 200))}
            maxLength={200}
            placeholder={t("admin.cohorts.namePlaceholder")}
          />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1.5">
            <Label className="text-xs">{t("admin.cohorts.fieldStart")}</Label>
            <DateTimePicker value={start} onChange={setStart} className="w-full" />
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs">{t("admin.cohorts.fieldEnd")}</Label>
            <DateTimePicker value={end} onChange={setEnd} className="w-full" />
          </div>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1.5">
            <Label className="text-xs">{t("admin.cohorts.fieldEnrollStart")}</Label>
            <DateTimePicker value={enrollStart} onChange={setEnrollStart} className="w-full" />
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs">{t("admin.cohorts.fieldEnrollEnd")}</Label>
            <DateTimePicker value={enrollEnd} onChange={setEnrollEnd} className="w-full" />
          </div>
        </div>
        <div className="space-y-1.5">
          <Label className="text-xs">{t("admin.cohorts.fieldMaxStudents")}</Label>
          <Input
            type="number"
            min={1}
            value={maxStudents}
            onChange={(e) => setMaxStudents(e.target.value.replace(/\D/g, "").slice(0, 5))}
            placeholder={t("admin.cohorts.maxStudentsPlaceholder")}
          />
        </div>
        <div className="flex justify-end gap-2 pt-2">
          <Button variant="outline" onClick={handleClose} disabled={saving}>
            {t("common.cancel")}
          </Button>
          <Button onClick={submit} disabled={!isValid || saving}>
            {saving ? t("admin.cohorts.creating") : t("admin.cohorts.create")}
          </Button>
        </div>
      </div>
    </Modal>
  )
}
