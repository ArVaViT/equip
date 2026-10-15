import { useEffect, useId, useState } from "react"
import { useTranslation } from "react-i18next"
import { isAxiosError } from "axios"
import { Scale } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Modal } from "@/components/patterns"
import { gradesService } from "@/services/grades"
import { getErrorContext } from "@/lib/errorCode"
import { getErrorDetail } from "@/lib/errorDetail"
import { toast } from "@/lib/toast"
import { formatNumber } from "@/i18n/number"
import { GRADING_SCHEMES, type GradingScheme, type GradingSchemeResponse } from "@/types"
import { describeBands } from "./bandRanges"
import type { GradeBand } from "./symbolScale"

/**
 * Spelled out rather than built from the value: the key-coverage check reads
 * literal keys only, and the four names already exist for the school settings.
 */
const SCHEME_LABEL_KEY: Record<GradingScheme, string> = {
  pass_fail: "gradingScheme.pass_fail",
  percent: "gradingScheme.percent",
  five_point: "gradingScheme.five_point",
  letter: "gradingScheme.letter",
}

function isScheme(value: string): value is GradingScheme {
  return (GRADING_SCHEMES as readonly string[]).includes(value)
}

/** Mirrors ``FIVE_POINT_MAX_THRESHOLD`` on the server; above it «3» is unreachable. */
const FIVE_POINT_MAX_THRESHOLD = 75

/**
 * The cheap half of the server's rules, so a director is told before the
 * round-trip. The server validates again and stays the authority: anything
 * it refuses that this let through is shown in the same place.
 */
function pairProblem(scheme: GradingScheme, threshold: number): "range" | "fivePoint" | null {
  if (!Number.isFinite(threshold) || threshold < 0 || threshold > 100) return "range"
  if (scheme === "five_point" && threshold > FIVE_POINT_MAX_THRESHOLD) return "fivePoint"
  return null
}

const whole = (n: number) => formatNumber(n, Number.isInteger(n) ? 0 : 1)

interface Props {
  courseId: string
  /** A director of the school (or platform staff) — the one who decides (D1). */
  canChange: boolean
  /** Called after a change lands, so the symbols on the page can be re-read. */
  onChanged: () => void
}

/**
 * How this course is graded, for everyone who can open the gradebook.
 *
 * A teacher could already see «B» next to a score and the pass line in the
 * student's view, but never the table that produced them, and never where the
 * course's scheme came from. It is the director's decision, and the block says
 * so in one line, so a teacher does not go looking for a control that is not
 * there — and a director finds the one that is.
 */
export function GradingScaleCard({ courseId, canChange, onChanged }: Props) {
  const { t } = useTranslation()
  const [scheme, setScheme] = useState<GradingSchemeResponse | null>(null)
  const [failed, setFailed] = useState(false)
  const [editing, setEditing] = useState(false)

  useEffect(() => {
    let cancelled = false
    setScheme(null)
    setFailed(false)
    gradesService
      .getGradingScheme(courseId)
      .then((s) => {
        if (!cancelled) setScheme(s)
      })
      .catch(() => {
        if (!cancelled) setFailed(true)
      })
    return () => {
      cancelled = true
    }
  }, [courseId])

  // Nothing to say yet: the block appears with its answer rather than as a
  // spinner above the table, and a failed read is one quiet line.
  if (failed) return <p className="mb-6 text-sm text-ink-muted">{t("gradebook.scale.loadFailed")}</p>
  if (!scheme) return null

  const bands: GradeBand[] = scheme.bands.map(([floor, symbol]) => [Number(floor), symbol])
  const schemeName = isScheme(scheme.grading_scheme)
    ? t(SCHEME_LABEL_KEY[scheme.grading_scheme])
    : scheme.grading_scheme

  return (
    <div className="mb-6 flex flex-col gap-3 rounded-lg border border-edge bg-muted/30 px-4 py-3 text-sm sm:flex-row sm:items-start sm:justify-between">
      <div className="min-w-0 space-y-0.5">
        <p className="flex items-center gap-1.5 font-medium">
          <Scale className="h-4 w-4 shrink-0 text-ink-muted" strokeWidth={1.75} aria-hidden />
          {t("gradebook.scale.title")}
        </p>
        <p className="first-letter:uppercase">
          {t("gradebook.scale.summary", {
            scheme: schemeName,
            threshold: whole(Number(scheme.pass_threshold)),
          })}
        </p>
        {bands.length > 0 && <p className="text-ink-muted">{describeBands(bands, whole)}</p>}
        {/* Who decides — said to the teacher; the director is the answer. */}
        {!canChange && <p className="text-xs text-ink-muted">{t("gradebook.scale.directorDecides")}</p>}
      </div>
      {canChange && (
        <>
          <Button size="sm" variant="outline" className="sm:shrink-0" onClick={() => setEditing(true)}>
            {t("gradebook.scale.change")}
          </Button>
          <ChangeSchemeDialog
            open={editing}
            courseId={courseId}
            current={scheme}
            onClose={() => setEditing(false)}
            onSaved={(next) => {
              setScheme(next)
              setEditing(false)
              toast({ title: t("toast.gradingSchemeSaved"), variant: "success" })
              onChanged()
            }}
          />
        </>
      )}
    </div>
  )
}

interface DialogProps {
  open: boolean
  courseId: string
  current: GradingSchemeResponse
  onClose: () => void
  onSaved: (next: GradingSchemeResponse) => void
}

/**
 * Scheme and pass line together — the server validates them as a pair (D8.1)
 * and so does the form.
 *
 * A refusal stays on screen with the form: a 409 means hand-set grades exist
 * under the old scheme, and the director's next step is to go and have them
 * cleared, not to retype the same values into a fresh dialog.
 */
function ChangeSchemeDialog({ open, courseId, current, onClose, onSaved }: DialogProps) {
  const { t } = useTranslation()
  const thresholdId = useId()
  const problemId = useId()
  const [draftScheme, setDraftScheme] = useState<GradingScheme>(
    isScheme(current.grading_scheme) ? current.grading_scheme : "letter",
  )
  const [draftThreshold, setDraftThreshold] = useState(String(Number(current.pass_threshold)))
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Reopen from the current values, not from the last attempt's.
  useEffect(() => {
    if (!open) return
    setDraftScheme(isScheme(current.grading_scheme) ? current.grading_scheme : "letter")
    setDraftThreshold(String(Number(current.pass_threshold)))
    setError(null)
  }, [open, current])

  const threshold = Number(draftThreshold.trim())
  const problem = draftThreshold.trim() === "" ? "range" : pairProblem(draftScheme, threshold)
  const problemText =
    problem === "range"
      ? t("gradebook.scale.thresholdRange")
      : problem === "fivePoint"
        ? t("gradebook.scale.fivePointMax")
        : null

  const save = async () => {
    if (problem || saving) return
    setSaving(true)
    setError(null)
    try {
      const next = await gradesService.updateGradingScheme(courseId, {
        grading_scheme: draftScheme,
        pass_threshold: threshold,
      })
      onSaved(next)
    } catch (err) {
      const status = isAxiosError(err) ? err.response?.status : undefined
      if (status === 409) {
        // The server names the students; the count is what the director
        // needs here, in words a teacher can be handed.
        const affected = getErrorContext(err)?.affected_students
        setError(
          Array.isArray(affected)
            ? t("gradebook.scale.handSetGrades", { count: affected.length })
            : t("gradebook.scale.handSetGradesUnknown"),
        )
      } else {
        setError(getErrorDetail(err))
      }
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal open={open} onClose={onClose} title={t("gradebook.scale.dialogTitle")}>
      <div className="space-y-4">
        <div className="space-y-1.5">
          <Label className="text-xs">{t("gradebook.scale.scheme")}</Label>
          <Select value={draftScheme} onValueChange={(v) => isScheme(v) && setDraftScheme(v)}>
            <SelectTrigger aria-label={t("gradebook.scale.scheme")}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {GRADING_SCHEMES.map((s) => (
                <SelectItem key={s} value={s}>
                  {t(SCHEME_LABEL_KEY[s])}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1.5 sm:max-w-[12rem]">
          <Label htmlFor={thresholdId} className="text-xs">
            {t("gradebook.scale.passThreshold")}
          </Label>
          <Input
            id={thresholdId}
            type="number"
            inputMode="decimal"
            min={0}
            max={draftScheme === "five_point" ? FIVE_POINT_MAX_THRESHOLD : 100}
            step={1}
            value={draftThreshold}
            onChange={(e) => setDraftThreshold(e.target.value)}
            fieldSize="md"
            // The objection belongs to this field: a screen reader reads it
            // with the field, not only once when it appears.
            aria-invalid={problemText ? true : undefined}
            aria-describedby={problemText ? problemId : undefined}
          />
        </div>
        {/* The form's own objection while typing, the server's after Save —
            one place, so the eye learns where to look. */}
        {(error ?? problemText) && (
          <p id={problemId} role="alert" className="text-sm text-destructive">
            {error ?? problemText}
          </p>
        )}
        <div className="flex justify-end gap-2 pt-2">
          <Button variant="outline" onClick={onClose} disabled={saving}>
            {t("common.cancel")}
          </Button>
          <Button onClick={save} disabled={saving || problem !== null}>
            {t("common.save")}
          </Button>
        </div>
      </div>
    </Modal>
  )
}
