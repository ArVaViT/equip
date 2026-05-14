import { useState } from "react"
import { useTranslation } from "react-i18next"
import { Modal } from "@/components/patterns"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { cohortsService } from "@/services/cohorts"
import { toast } from "@/lib/toast"

interface Props {
  open: boolean
  onClose: () => void
  cohortId: string
  onAdded: () => void
}

/** Add a student to the cohort by email. Backend resolves email →
 *  existing platform user; the student must already have signed up. */
export function AddStudentDialog({ open, onClose, cohortId, onAdded }: Props) {
  const { t } = useTranslation()
  const [email, setEmail] = useState("")
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleClose = () => {
    if (saving) return
    setEmail("")
    setError(null)
    onClose()
  }

  const isValid = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)

  const submit = async () => {
    if (!isValid) return
    setSaving(true)
    setError(null)
    try {
      await cohortsService.addCohortStudent(cohortId, { email })
      toast({ title: t("admin.cohorts.toast.studentAdded"), variant: "success" })
      setEmail("")
      onAdded()
    } catch (e: unknown) {
      const status = (e as { response?: { status?: number } })?.response?.status
      if (status === 404) {
        setError(t("admin.cohorts.errorUserNotFound"))
      } else if (status === 403) {
        setError(t("admin.cohorts.errorCohortFull"))
      } else {
        toast({ title: t("admin.cohorts.toast.addStudentFailed"), variant: "destructive" })
      }
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal open={open} onClose={handleClose} title={t("admin.cohorts.addStudentTitle")}>
      <div className="space-y-4">
        <p className="text-xs text-muted-foreground">
          {t("admin.cohorts.addStudentHint")}
        </p>
        <div className="space-y-1.5">
          <Label className="text-xs">{t("admin.cohorts.fieldEmail")}</Label>
          <Input
            type="email"
            value={email}
            onChange={(e) => {
              setEmail(e.target.value.slice(0, 254))
              setError(null)
            }}
            placeholder={t("admin.cohorts.emailPlaceholder")}
            maxLength={254}
            onKeyDown={(e) => {
              if (e.key === "Enter" && isValid && !saving) void submit()
            }}
          />
          {error && <p className="text-xs text-destructive">{error}</p>}
        </div>
        <div className="flex justify-end gap-2 pt-2">
          <Button variant="outline" onClick={handleClose} disabled={saving}>
            {t("common.cancel")}
          </Button>
          <Button onClick={submit} disabled={!isValid || saving}>
            {saving ? t("admin.cohorts.adding") : t("admin.cohorts.add")}
          </Button>
        </div>
      </div>
    </Modal>
  )
}
