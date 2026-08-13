import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { Loader2, Plus, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { rubricsService } from "@/services/rubrics"
import { toast } from "@/lib/toast"
import { getErrorDetail } from "@/lib/errorDetail"
import { RubricGrid } from "./RubricGrid"
import type { Rubric } from "@/types"

interface Draft {
  title: string
  criteria: { title: string; levels: { label: string; points: number }[] }[]
}

/**
 * Building a marking standard, and attaching it to an assignment.
 *
 * The API, the grid and the marking rules all shipped without this, so a
 * rubric could only enter the product by a direct API call — which means the
 * one mechanism that makes marking tap-only on a phone was unreachable by the
 * person it was built for.
 *
 * The editor is the same grid the teacher will later tap, filled in rather
 * than chosen from. That is deliberate: a rubric authored in a different shape
 * from the one it is used in is a rubric whose author cannot see what they are
 * making.
 *
 * Defaults do the work. A new rubric arrives with three criteria and three
 * levels already named, because a blank grid is where this feature dies — the
 * teacher opens it, sees an empty table and a Save button, and closes it.
 */
export function RubricEditor({
  courseId,
  assignmentId,
  onAttached,
}: {
  courseId: string
  assignmentId: string
  onAttached?: (rubric: Rubric) => void
}) {
  const { t } = useTranslation()
  const [existing, setExisting] = useState<Rubric[] | null>(null)
  const [attached, setAttached] = useState<Rubric | null>(null)
  const [busy, setBusy] = useState(false)
  const [draft, setDraft] = useState<Draft | null>(null)

  useEffect(() => {
    let cancelled = false
    rubricsService
      .listForCourse(courseId)
      // A course with no rubrics yet is the ordinary case, and a failed list
      // must not hide the button that creates the first one.
      .catch(() => [] as Rubric[])
      .then((list) => {
        if (!cancelled) setExisting(list)
      })
    return () => {
      cancelled = true
    }
  }, [courseId])

  const startDraft = () =>
    setDraft({
      title: t("rubricEditor.defaultTitle"),
      criteria: [
        { title: "", levels: defaultLevels(t) },
        { title: "", levels: defaultLevels(t) },
        { title: "", levels: defaultLevels(t) },
      ],
    })

  const attach = async (rubricId: string) => {
    setBusy(true)
    try {
      const rubric = await rubricsService.attach(assignmentId, rubricId)
      setAttached(rubric)
      onAttached?.(rubric)
      toast({ title: t("rubricEditor.attached"), variant: "success" })
    } catch (err) {
      toast({ title: getErrorDetail(err, t("rubricEditor.attachFailed")), variant: "destructive" })
    } finally {
      setBusy(false)
    }
  }

  const save = async () => {
    if (!draft) return
    const criteria = draft.criteria
      .filter((c) => c.title.trim())
      .map((c) => ({ title: c.title.trim(), levels: c.levels }))
    if (criteria.length === 0) {
      toast({ title: t("rubricEditor.needCriterion"), variant: "destructive" })
      return
    }
    setBusy(true)
    try {
      const rubric = await rubricsService.create({
        course_id: courseId,
        title: draft.title.trim() || t("rubricEditor.defaultTitle"),
        criteria,
      })
      setDraft(null)
      setExisting((prev) => [rubric, ...(prev ?? [])])
      // Creating one and not attaching it is a rubric nobody marks with, so
      // the two are one action from the teacher's side.
      await attach(rubric.id)
    } catch (err) {
      toast({ title: getErrorDetail(err, t("rubricEditor.saveFailed")), variant: "destructive" })
    } finally {
      setBusy(false)
    }
  }

  if (attached) {
    return (
      <div className="space-y-2">
        <p className="text-xs uppercase tracking-[0.18em] text-ink-muted">
          {t("rubricEditor.attachedHeading")}
        </p>
        {/* The grid, read-only — the teacher sees exactly what they will tap. */}
        <RubricGrid rubric={attached} marks={[]} />
      </div>
    )
  }

  if (draft) {
    return (
      <div className="space-y-3">
        <Input
          value={draft.title}
          onChange={(e) => setDraft({ ...draft, title: e.target.value })}
          aria-label={t("rubricEditor.titleLabel")}
          fieldSize="sm"
        />
        {draft.criteria.map((criterion, ci) => (
          <div key={ci} className="rounded-md border border-edge p-2.5">
            <div className="flex items-center gap-2">
              <Input
                value={criterion.title}
                placeholder={t("rubricEditor.criterionPlaceholder")}
                fieldSize="sm"
                onChange={(e) => {
                  const next = [...draft.criteria]
                  next[ci] = { ...criterion, title: e.target.value }
                  setDraft({ ...draft, criteria: next })
                }}
              />
              <Button
                variant="ghost"
                size="sm"
                aria-label={t("rubricEditor.removeCriterion")}
                onClick={() =>
                  setDraft({ ...draft, criteria: draft.criteria.filter((_, i) => i !== ci) })
                }
              >
                <X className="h-4 w-4" strokeWidth={1.75} aria-hidden />
              </Button>
            </div>
            <div className="mt-2 grid grid-cols-3 gap-2">
              {criterion.levels.map((level, li) => (
                <div key={li} className="flex items-center gap-1">
                  <Input
                    value={level.label}
                    fieldSize="sm"
                    aria-label={t("rubricEditor.levelLabel")}
                    onChange={(e) => {
                      const next = [...draft.criteria]
                      const levels = [...criterion.levels]
                      levels[li] = { ...level, label: e.target.value }
                      next[ci] = { ...criterion, levels }
                      setDraft({ ...draft, criteria: next })
                    }}
                  />
                  <Input
                    type="number"
                    min={0}
                    value={level.points}
                    className="w-16"
                    fieldSize="sm"
                    aria-label={t("rubricEditor.levelPoints")}
                    onChange={(e) => {
                      const next = [...draft.criteria]
                      const levels = [...criterion.levels]
                      levels[li] = { ...level, points: Math.max(0, Number(e.target.value) || 0) }
                      next[ci] = { ...criterion, levels }
                      setDraft({ ...draft, criteria: next })
                    }}
                  />
                </div>
              ))}
            </div>
          </div>
        ))}
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() =>
              setDraft({
                ...draft,
                criteria: [...draft.criteria, { title: "", levels: defaultLevels(t) }],
              })
            }
          >
            <Plus className="mr-1.5 h-4 w-4" strokeWidth={1.75} aria-hidden />
            {t("rubricEditor.addCriterion")}
          </Button>
          <Button size="sm" onClick={save} disabled={busy}>
            {busy && <Loader2 className="mr-1.5 h-4 w-4 animate-spin" strokeWidth={1.75} aria-hidden />}
            {t("rubricEditor.saveAndAttach")}
          </Button>
          <Button variant="ghost" size="sm" onClick={() => setDraft(null)}>
            {t("common.cancel")}
          </Button>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-2">
      <p className="text-sm text-ink-muted">{t("rubricEditor.why")}</p>
      <div className="flex flex-wrap items-center gap-2">
        <Button size="sm" variant="outline" onClick={startDraft} disabled={busy}>
          <Plus className="mr-1.5 h-4 w-4" strokeWidth={1.75} aria-hidden />
          {t("rubricEditor.create")}
        </Button>
        {/* Reuse before re-typing: «наша стандартная рубрика эссе» is the
            thing a school actually wants, and it is why rubrics are scoped to
            the course rather than to one assignment. */}
        {existing?.map((r) => (
          <Button key={r.id} size="sm" variant="ghost" disabled={busy} onClick={() => attach(r.id)}>
            {r.title} · {r.max_score}
          </Button>
        ))}
      </div>
    </div>
  )
}

function defaultLevels(t: (k: string) => string) {
  // Named, not blank. A grid of empty cells is where this feature dies.
  return [
    { label: t("rubricEditor.levelWeak"), points: 0 },
    { label: t("rubricEditor.levelOk"), points: 5 },
    { label: t("rubricEditor.levelStrong"), points: 10 },
  ]
}
