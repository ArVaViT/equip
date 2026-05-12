import { useTranslation } from "react-i18next"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Settings2, ChevronDown, ChevronRight, Save } from "lucide-react"
import type { GradingConfig } from "@/types"

interface Props {
  open: boolean
  onToggle: () => void
  draft: GradingConfig
  onDraftChange: (next: GradingConfig) => void
  onSave: () => void
  saving: boolean
}

/**
 * Collapsible card where a teacher edits the quiz/assignment/participation
 * weight split. The component enforces that the three weights must sum
 * to 100 before the save button becomes clickable.
 */
export function GradingConfigCard({
  open,
  onToggle,
  draft,
  onDraftChange,
  onSave,
  saving,
}: Props) {
  const { t } = useTranslation()
  const total = draft.quiz_weight + draft.assignment_weight + draft.participation_weight
  const valid = total === 100

  return (
    <Card className="mb-6">
      <CardHeader className="cursor-pointer select-none py-4" onClick={onToggle}>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Settings2 className="h-5 w-5 text-muted-foreground" strokeWidth={1.75} aria-hidden />
            <div>
              <CardTitle className="text-base">{t("gradebook.config.title")}</CardTitle>
              <CardDescription className="text-xs">
                {t("gradebook.config.description")}
              </CardDescription>
            </div>
          </div>
          {open ? (
            <ChevronDown className="h-4 w-4 text-muted-foreground" strokeWidth={1.75} aria-hidden />
          ) : (
            <ChevronRight className="h-4 w-4 text-muted-foreground" strokeWidth={1.75} aria-hidden />
          )}
        </div>
      </CardHeader>
      {open && (
        <CardContent className="border-t pt-6">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-6">
            <WeightField
              label={t("gradebook.config.quizWeight")}
              value={draft.quiz_weight}
              onChange={(v) => onDraftChange({ ...draft, quiz_weight: v })}
            />
            <WeightField
              label={t("gradebook.config.assignmentWeight")}
              value={draft.assignment_weight}
              onChange={(v) => onDraftChange({ ...draft, assignment_weight: v })}
            />
            <WeightField
              label={t("gradebook.config.participationWeight")}
              value={draft.participation_weight}
              onChange={(v) => onDraftChange({ ...draft, participation_weight: v })}
            />
          </div>
          <div className="flex items-center justify-between mt-4">
            <p
              className={`text-sm font-medium ${
                valid ? "text-success" : "text-destructive"
              }`}
            >
              {valid
                ? t("gradebook.config.totalValid", { total })
                : t("gradebook.config.totalInvalid", { total })}
            </p>
            <Button size="sm" onClick={onSave} disabled={!valid || saving}>
              <Save className="mr-1.5 h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
              {saving ? t("gradebook.config.saving") : t("gradebook.config.save")}
            </Button>
          </div>
        </CardContent>
      )}
    </Card>
  )
}

interface WeightFieldProps {
  label: string
  value: number
  onChange: (next: number) => void
}

function WeightField({ label, value, onChange }: WeightFieldProps) {
  return (
    <div className="space-y-2">
      <Label>{label}</Label>
      <Input
        type="number"
        min={0}
        max={100}
        value={value}
        onChange={(e) => onChange(Number(e.target.value) || 0)}
        fieldSize="md"
      />
    </div>
  )
}
