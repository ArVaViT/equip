import { useState, useEffect } from "react"
import { useTranslation } from "react-i18next"
import { Check, Lock, Globe, Save } from "lucide-react"
import { Modal } from "@/components/patterns"
import { Button } from "@/components/ui/button"

interface Props {
  open: boolean
  onClose: () => void
  current: "public" | "institute"
  saving: boolean
  onSave: (next: "public" | "institute") => void | Promise<void>
}

/**
 * Admin-only access mode toggle (ADR-010). Slotted into the teacher's
 * CourseEditor kebab menu but rendered conditionally based on the
 * viewer's role.
 *
 * - public: anyone who's signed in can self-enroll (subject to the
 *   enrollment window).
 * - institute: enroll button is replaced with a "By invitation only"
 *   notice; only an admin attaching the student to a cohort enrolls
 *   them in this course.
 */
export function AccessModeModal({ open, onClose, current, saving, onSave }: Props) {
  const { t } = useTranslation()
  const [choice, setChoice] = useState<"public" | "institute">(current)

  useEffect(() => {
    if (open) setChoice(current)
  }, [open, current])

  return (
    <Modal open={open} onClose={onClose} title={t("courseEditor.accessMode.title")}>
      <div className="space-y-3">
        <Option
          checked={choice === "public"}
          onSelect={() => setChoice("public")}
          icon={<Globe className="h-4 w-4" strokeWidth={1.75} aria-hidden />}
          label={t("courseEditor.accessMode.publicLabel")}
          description={t("courseEditor.accessMode.publicDescription")}
        />
        <Option
          checked={choice === "institute"}
          onSelect={() => setChoice("institute")}
          icon={<Lock className="h-4 w-4" strokeWidth={1.75} aria-hidden />}
          label={t("courseEditor.accessMode.instituteLabel")}
          description={t("courseEditor.accessMode.instituteDescription")}
        />
        <div className="flex justify-end gap-2 pt-2">
          <Button variant="outline" onClick={onClose} disabled={saving}>
            {t("common.cancel")}
          </Button>
          <Button
            onClick={() => void onSave(choice)}
            disabled={saving || choice === current}
          >
            <Save className="h-4 w-4 mr-1.5" strokeWidth={1.75} aria-hidden />
            {saving ? t("courseEditor.accessMode.saving") : t("courseEditor.accessMode.save")}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

interface OptionProps {
  checked: boolean
  onSelect: () => void
  icon: React.ReactNode
  label: string
  description: string
}

function Option({ checked, onSelect, icon, label, description }: OptionProps) {
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-pressed={checked}
      className={`w-full text-left rounded-md border p-3 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 ${
        checked
          ? "border-primary bg-primary/[0.08] dark:bg-primary/15"
          : "border-border hover:border-primary/40"
      }`}
    >
      <div className="flex items-center gap-2 mb-1">
        {icon}
        <span className="font-medium text-sm">{label}</span>
        {checked && (
          <Check
            className="ml-auto h-4 w-4 text-primary"
            strokeWidth={1.75}
            aria-hidden
          />
        )}
      </div>
      <p className="text-xs text-muted-foreground leading-relaxed">{description}</p>
    </button>
  )
}
