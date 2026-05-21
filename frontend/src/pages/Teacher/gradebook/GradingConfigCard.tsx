import { useId } from "react"
import { useTranslation } from "react-i18next"
import { Card, CardContent, CardTitle, CardDescription } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Settings2, ChevronDown, Save } from "lucide-react"
import { cn } from "@/lib/utils"
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
  // Stable id used for ``aria-controls`` so a screen-reader user
  // pressing Enter/Space on the trigger knows which panel just opened.
  const panelId = useId()

  return (
    <Card className="mb-6">
      {/* Trigger is a real ``<button>`` (not a div+onClick) so it gets
          keyboard activation, focus ring, and disclosure semantics for
          free. ``aria-expanded`` + ``aria-controls`` complete the
          disclosure-widget contract; the chevron animates the same
          state visually. */}
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        aria-controls={panelId}
        className="flex w-full select-none items-center justify-between rounded-t-md p-5 text-left transition-colors hover:bg-muted/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
      >
        <div className="flex items-center gap-2">
          <Settings2 className="h-5 w-5 text-muted-foreground" strokeWidth={1.75} aria-hidden />
          <div>
            <CardTitle className="text-base">{t("gradebook.config.title")}</CardTitle>
            <CardDescription className="text-xs">
              {t("gradebook.config.description")}
            </CardDescription>
          </div>
        </div>
        <ChevronDown
          className={cn(
            "h-4 w-4 shrink-0 text-muted-foreground transition-transform duration-200",
            open ? "rotate-0" : "-rotate-90",
          )}
          strokeWidth={1.75}
          aria-hidden
        />
      </button>
      {open && (
        <CardContent id={panelId} className="border-t pt-6">
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
        onChange={(e) => {
          // ``Number(e.target.value) || 0`` masked invalid input by
          // silently coercing -50, 1e10, NaN, "abc" to 0 or to garbage.
          // ``min``/``max`` are HTML hints only -- the browser accepts
          // any number-shaped string. Clamp into [0, 100] and floor to
          // an int so a teacher pasting "-50" or "1e9" can't poison
          // the weights and force a "must sum to 100" trap they can't
          // see why.
          const raw = Number(e.target.value)
          if (!Number.isFinite(raw)) {
            onChange(0)
            return
          }
          onChange(Math.max(0, Math.min(100, Math.floor(raw))))
        }}
        fieldSize="md"
      />
    </div>
  )
}
