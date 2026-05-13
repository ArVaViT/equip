import { useEffect } from "react"
import { useTranslation } from "react-i18next"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Save } from "lucide-react"
import { Modal } from "@/components/patterns"
import { EnrollmentStatusBadge } from "./badges"

interface Props {
  open: boolean
  onClose: () => void
  start: string
  end: string
  onStartChange: (next: string) => void
  onEndChange: (next: string) => void
  saving: boolean
  onSave: () => void | Promise<void>
}

/** Single enrollment-period editor. Ctrl/⌘+S shortcut is wired here. */
export function EnrollmentModal({
  open,
  onClose,
  start,
  end,
  onStartChange,
  onEndChange,
  saving,
  onSave,
}: Props) {
  const { t } = useTranslation()
  useEffect(() => {
    if (!open) return
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "s") {
        e.preventDefault()
        void onSave()
      }
    }
    document.addEventListener("keydown", handleKeyDown)
    return () => document.removeEventListener("keydown", handleKeyDown)
  }, [open, onSave])

  return (
    <Modal open={open} onClose={onClose} title={t("teacherEditor.modals.enrollment.title")}>
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <Label className="font-medium">{t("teacherEditor.modals.enrollment.status")}</Label>
          <EnrollmentStatusBadge start={start} end={end} />
        </div>
        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-1.5">
            <Label className="text-xs">{t("teacherEditor.modals.enrollment.start")}</Label>
            <Input
              type="datetime-local"
              value={start}
              onChange={(e) => onStartChange(e.target.value)}
              className="text-sm"
            />
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs">{t("teacherEditor.modals.enrollment.end")}</Label>
            <Input
              type="datetime-local"
              value={end}
              onChange={(e) => onEndChange(e.target.value)}
              className="text-sm"
            />
          </div>
        </div>
        <Button onClick={onSave} disabled={saving} className="w-full">
          <Save className="h-4 w-4 mr-1.5" />
          {saving
            ? t("teacherEditor.modals.enrollment.saving")
            : t("teacherEditor.modals.enrollment.save")}
        </Button>
      </div>
    </Modal>
  )
}
