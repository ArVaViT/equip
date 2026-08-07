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
 * Collapsible card where a teacher splits the course grade between quizzes
 * and assignments.
 *
 * Two changes from the three-field version, both in service of the same goal —
 * a teacher should not be able to get this wrong:
 *
 * 1. "Participation" is gone (D5). It duplicated course progress and counted
 *    every passed quiz twice, and no Bible-college handbook in the redesign
 *    research treats it as a weighted category.
 * 2. The two remaining weights are complementary, so editing one sets the
 *    other. The old card let a teacher type 30 and 50, then blocked Save with
 *    "must sum to 100" — an error state that existed only because the form
 *    asked for a number it could compute itself.
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
  // Complementary by construction — the invalid state is unreachable.
  const setSplit = (quiz: number) =>
    onDraftChange({
      ...draft,
      quiz_weight: quiz,
      assignment_weight: 100 - quiz,
      participation_weight: 0,
    })
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
        className="flex w-full select-none items-center justify-between rounded-t-md p-5 text-left transition-colors hover:bg-muted/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2"
      >
        <div className="flex items-center gap-2">
          <Settings2 className="h-5 w-5 text-ink-muted" strokeWidth={1.75} aria-hidden />
          <div>
            <CardTitle>{t("gradebook.config.title")}</CardTitle>
            <CardDescription className="text-xs">
              {t("gradebook.config.description")}
            </CardDescription>
          </div>
        </div>
        <ChevronDown
          className={cn(
            "h-4 w-4 shrink-0 text-ink-muted transition-transform duration-200",
            open ? "rotate-0" : "-rotate-90",
          )}
          strokeWidth={1.75}
          aria-hidden
        />
      </button>
      {open && (
        <CardContent id={panelId} className="border-t pt-6">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
            <WeightField
              label={t("gradebook.config.quizWeight")}
              value={draft.quiz_weight}
              onChange={setSplit}
            />
            <WeightField
              label={t("gradebook.config.assignmentWeight")}
              value={draft.assignment_weight}
              onChange={(v) => setSplit(100 - v)}
            />
          </div>
          <div className="flex items-center justify-between mt-4">
            <p className="text-sm font-medium text-ink-muted">
              {t("gradebook.config.split", {
                quiz: draft.quiz_weight,
                assignment: draft.assignment_weight,
              })}
            </p>
            <Button size="sm" onClick={onSave} disabled={saving}>
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
