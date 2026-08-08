import { memo, useMemo } from "react"
import { useTranslation, Trans } from "react-i18next"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { EmptyState } from "@/components/patterns"
import {
  ChevronDown, ChevronRight,
  ArrowUp, ArrowDown, ArrowUpDown,
  Save, Award, MessageSquare, Users,
} from "lucide-react"
import type {
  GradeSummaryResponse,
  StudentGrade,
  StudentCalculatedGrade,
} from "@/types"
import {
  LETTER_ORDER,
  type SortField,
  type SortDir,
  type GradeForm,
} from "./types"
import { EMPTY_FORM, letterColor } from "./helpers"
import { gradebookNotice, gradePillLabel } from "./notice"

interface Props {
  summary: GradeSummaryResponse | null
  manualGrades: Map<string, StudentGrade>
  forms: Map<string, GradeForm>
  saving: string | null
  expandedId: string | null
  sortField: SortField
  sortDir: SortDir
  onSortChange: (field: SortField, dir: SortDir) => void
  onToggleExpand: (userId: string) => void
  onUpdateForm: (userId: string, field: keyof GradeForm, value: string) => void
  onSaveGrade: (userId: string) => void
}

/**
 * "Summary Grades" tab: auto-calculated quiz/assignment
 * breakdown per student with an inline panel for manual grade overrides.
 */
export function SummaryTab({
  summary,
  manualGrades,
  forms,
  saving,
  expandedId,
  sortField,
  sortDir,
  onSortChange,
  onToggleExpand,
  onUpdateForm,
  onSaveGrade,
}: Props) {
  const { t } = useTranslation()
  const sortedStudents = useMemo(() => {
    if (!summary) return []
    const list = [...summary.students]
    const dir = sortDir === "asc" ? 1 : -1
    list.sort((a, b) => {
      let cmp = 0
      switch (sortField) {
        case "name":
          cmp = (a.student_name ?? "").localeCompare(b.student_name ?? "")
          break
        case "quiz":
          cmp = a.breakdown.quiz_avg - b.breakdown.quiz_avg
          break
        case "assignment":
          cmp = a.breakdown.assignment_avg - b.breakdown.assignment_avg
          break
        case "final":
          cmp = a.breakdown.final_score - b.breakdown.final_score
          break
        case "letter":
          cmp =
            (LETTER_ORDER[a.breakdown.letter_grade] ?? 0) -
            (LETTER_ORDER[b.breakdown.letter_grade] ?? 0)
          break
      }
      return cmp * dir
    })
    return list
  }, [summary, sortField, sortDir])

  const studentCount = sortedStudents.length
  const classAvg = summary?.class_average ?? null

  const toggleSort = (field: SortField) => {
    if (sortField === field) {
      onSortChange(field, sortDir === "asc" ? "desc" : "asc")
    } else {
      onSortChange(field, field === "name" ? "asc" : "desc")
    }
  }

  // Course-level facts, not per-student: the calculator resolves both from the
  // course, so any row carries the same answer. Shown once at the top because
  // an explanation buried inside an expandable row is an explanation nobody
  // reads — the teacher sees a table of dashes and rings support instead.
  // One place decides what the gradebook explains — see notice.ts for why.
  const first = sortedStudents[0]?.breakdown
  const noticeKey = gradebookNotice(first, summary?.config)

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("gradebook.summary.title")}</CardTitle>
        <CardDescription>{t("gradebook.summary.description")}</CardDescription>
      </CardHeader>
      <CardContent>
        {noticeKey && (
          <div className="mb-4 rounded border-l-stripe border-l-info bg-info/10 px-3 py-2 text-sm text-ink">
            {t(noticeKey)}
          </div>
        )}
        {studentCount === 0 ? (
          <EmptyState
            variant="compact"
            icon={<Users strokeWidth={1.75} aria-hidden />}
            title={t("gradebook.summary.empty")}
          />
        ) : (
          <div className="overflow-x-auto">
            <div className="grid grid-cols-[1fr_80px_80px_80px_70px_70px] gap-3 px-4 py-3 border-b bg-muted/30 rounded-t-lg min-w-[700px]">
              <SortHeader field="name" label={t("gradebook.summary.thStudent")} sortField={sortField} sortDir={sortDir} onToggle={toggleSort} />
              <SortHeader field="quiz" label={t("gradebook.summary.thQuiz")} sortField={sortField} sortDir={sortDir} onToggle={toggleSort} className="justify-end" />
              <SortHeader field="assignment" label={t("gradebook.summary.thAssignment")} sortField={sortField} sortDir={sortDir} onToggle={toggleSort} className="justify-end" />
              <SortHeader field="final" label={t("gradebook.summary.thFinal")} sortField={sortField} sortDir={sortDir} onToggle={toggleSort} className="justify-end" />
              <SortHeader field="letter" label={t("gradebook.summary.thGrade")} sortField={sortField} sortDir={sortDir} onToggle={toggleSort} className="justify-center" />
              <span className="text-xs font-semibold uppercase tracking-wider text-ink-muted text-center">{t("gradebook.summary.thManual")}</span>
            </div>

            <div className="divide-y min-w-[700px]">
              {sortedStudents.map((student) => (
                <StudentSummaryRow
                  key={student.student_id}
                  student={student}
                  manualGrade={manualGrades.get(student.student_id)}
                  form={forms.get(student.student_id) ?? EMPTY_FORM}
                  expanded={expandedId === student.student_id}
                  saving={saving === student.student_id}
                  onToggleExpand={onToggleExpand}
                  onUpdateForm={onUpdateForm}
                  onSaveGrade={onSaveGrade}
                />
              ))}

              {summary && studentCount > 0 && (
                <ClassAverageRow
                  summary={summary}
                  studentCount={studentCount}
                  classAvg={classAvg}
                />
              )}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

interface SortHeaderProps {
  field: SortField
  label: string
  sortField: SortField
  sortDir: SortDir
  onToggle: (field: SortField) => void
  className?: string
}

function SortHeader({ field, label, sortField, sortDir, onToggle, className }: SortHeaderProps) {
  const active = sortField === field
  return (
    <button
      onClick={() => onToggle(field)}
      className={`flex items-center gap-1 text-xs font-semibold uppercase tracking-wider text-ink-muted hover:text-ink transition-colors ${
        className ?? ""
      }`}
    >
      {label}
      {active ? (
        sortDir === "asc" ? (
          <ArrowUp className="h-3.5 w-3.5" strokeWidth={1.75} />
        ) : (
          <ArrowDown className="h-3.5 w-3.5" strokeWidth={1.75} />
        )
      ) : (
        <ArrowUpDown className="h-3.5 w-3.5 opacity-40" strokeWidth={1.75} />
      )}
    </button>
  )
}

interface StudentSummaryRowProps {
  student: StudentCalculatedGrade
  manualGrade: StudentGrade | undefined
  form: GradeForm
  expanded: boolean
  saving: boolean
  onToggleExpand: (userId: string) => void
  onUpdateForm: (userId: string, field: keyof GradeForm, value: string) => void
  onSaveGrade: (userId: string) => void
}

/**
 * Per-student row. Memoised so a keystroke in one row's override form
 * (which mutates the parent's `forms` map → re-renders SummaryTab) does
 * not also re-render every other row. All callback props are stable via
 * `useCallback` in `TeacherGradebook` and the default `form` is the
 * shared `EMPTY_FORM` constant, so the shallow-props compare actually
 * catches.
 */
const StudentSummaryRow = memo(function StudentSummaryRow({
  student,
  manualGrade,
  form,
  expanded,
  saving,
  onToggleExpand,
  onUpdateForm,
  onSaveGrade,
}: StudentSummaryRowProps) {
  const { t } = useTranslation()
  const b = student.breakdown
  const hasScore = b.result_state === "graded"
  // Only meaningful when there is a computed grade to differ *from*. On a
  // course with nothing to grade the computed symbol is empty, so any manual
  // grade would flag as "differs from  (0.0%)" — printing the very zero this
  // whole change exists to remove, in the one place a teacher is expected to
  // grade by hand.
  const hasDifferentManual =
    hasScore && Boolean(manualGrade?.grade && manualGrade.grade !== b.letter_grade)

  return (
    <div>
      <div
        className="grid cursor-pointer grid-cols-[1fr_80px_80px_80px_70px_70px] items-center gap-3 px-4 py-3 transition-colors hover:bg-muted/40"
        onClick={() => onToggleExpand(student.student_id)}
      >
        <div className="flex items-center gap-2 min-w-0">
          {expanded ? (
            <ChevronDown className="h-3.5 w-3.5 shrink-0 text-ink-muted" strokeWidth={1.75} />
          ) : (
            <ChevronRight className="h-3.5 w-3.5 shrink-0 text-ink-muted" strokeWidth={1.75} />
          )}
          <div className="min-w-0">
            <p className="text-sm font-medium truncate">{student.student_name || t("gradebook.summary.unknownStudent")}</p>
            <p className="text-xs text-ink-muted truncate">{student.student_email}</p>
          </div>
        </div>
        {/* A course with nothing gradable has no percentage. Printing 0.0%
            and an empty grade pill reads as "everyone failed" — the single
            most alarming thing a teacher can open the gradebook to. */}
        {/* No number exists in two cases — a course with nothing gradable, and
            a course nobody has been marked in yet. Printing 0.0% and an empty
            grade pill in either reads as "everyone failed". */}
        {/* In `zero_weighted` the category averages are real marks that simply
            carry no weight — hiding them behind a dash would deny the teacher
            figures that exist. Only the final score is absent. */}
        <p className="text-sm tabular-nums text-right">
          {hasScore || b.result_state === "zero_weighted" ? `${b.quiz_avg.toFixed(1)}%` : "—"}
        </p>
        <p className="text-sm tabular-nums text-right">
          {hasScore || b.result_state === "zero_weighted" ? `${b.assignment_avg.toFixed(1)}%` : "—"}
        </p>
        <p className="text-sm font-semibold tabular-nums text-right">
          {hasScore ? `${b.final_score.toFixed(1)}%` : "—"}
        </p>
        <div className="flex justify-center">
          {hasScore ? (
            <span className={`inline-flex items-center justify-center rounded-full px-2.5 py-0.5 text-xs font-bold ${letterColor(b.letter_grade)}`}>
              {b.letter_grade}
            </span>
          ) : (
            // Deliberately neutral. `completion_pass` is a fact about the
            // course having nothing to grade — not a statement that this
            // student passed, which still depends on their progress. A green
            // «Зачёт» here would award a pass to someone who has not opened a
            // single chapter.
            <span className="inline-flex items-center justify-center rounded-full bg-muted px-2.5 py-0.5 text-xs font-medium text-ink-muted">
              {t(gradePillLabel(b.result_state) ?? "")}
            </span>
          )}
        </div>
        <div className="flex justify-center">
          {manualGrade?.grade ? (
            <span
              className={`inline-flex items-center justify-center rounded-full px-2.5 py-0.5 text-xs font-bold ${
                hasDifferentManual
                  ? "bg-warning/15 text-warning ring-1 ring-warning/30"
                  : "bg-muted text-ink-muted"
              }`}
            >
              {manualGrade.grade}
            </span>
          ) : (
            <span className="text-xs text-ink-muted">—</span>
          )}
        </div>
      </div>

      {expanded && (
        <div className="border-t px-4 py-4 bg-muted/10 space-y-4">
          {hasScore ? (
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-x-6 gap-y-2 text-sm">
              {/* Only the categories that carry the score are shown, with the
                  weights actually applied. Printing «0.0% (×0% = 0.0)» for a
                  category that took no part looks like a mark of zero. */}
              {/* A category is hidden only when it holds nothing — never
                  because its weight is zero. Marks that exist must stay
                  visible, with «(×0% = 0.0)» showing exactly why they do not
                  move the total; dropping the row leaves 80% in the table
                  above with no explanation anywhere on the page. */}
              {(b.effective_quiz_weight > 0 || b.has_quiz_items) && (
                <BreakdownEntry
                  label={t("gradebook.summary.breakdownQuiz")}
                  pct={b.quiz_avg}
                  weight={b.effective_quiz_weight}
                  weighted={b.quiz_weighted}
                />
              )}
              {(b.effective_assignment_weight > 0 || b.has_assignment_items) && (
                <BreakdownEntry
                  label={t("gradebook.summary.breakdownAssignment")}
                  pct={b.assignment_avg}
                  weight={b.effective_assignment_weight}
                  weighted={b.assignment_weighted}
                />
              )}
            </div>
          ) : (
            // The course-level banner above already says why there is no
            // number; repeating it per row would be noise. State the student
            // fact instead.
            <p className="text-xs text-ink-muted">
              {t("gradebook.summary.noScoreForStudent")}
            </p>
          )}

          {hasDifferentManual && (
            <div className="rounded border-l-stripe border-l-warning bg-warning/10 px-3 py-2 text-xs text-ink">
              <Trans
                i18nKey="gradebook.summary.manualDiffers"
                values={{
                  manual: manualGrade?.grade ?? "",
                  calc: b.letter_grade,
                  pct: b.final_score.toFixed(1),
                }}
                components={{ strong: <strong /> }}
              />
            </div>
          )}

          <div className="grid grid-cols-1 sm:grid-cols-[120px_1fr] gap-3">
            <div className="space-y-1.5">
              <label className="flex items-center gap-1 text-xs font-medium">
                <Award className="h-3.5 w-3.5" strokeWidth={1.75} /> {t("gradebook.summary.overrideGrade")}
              </label>
              <Input
                value={form.grade}
                onChange={(e) => onUpdateForm(student.student_id, "grade", e.target.value)}
                placeholder={t("gradebook.summary.overridePlaceholder")}
                fieldSize="md"
              />
            </div>
            <div className="space-y-1.5">
              <label className="flex items-center gap-1 text-xs font-medium">
                <MessageSquare className="h-3.5 w-3.5" strokeWidth={1.75} /> {t("gradebook.summary.comment")}
              </label>
              <Input
                value={form.comment}
                onChange={(e) => onUpdateForm(student.student_id, "comment", e.target.value)}
                placeholder={t("gradebook.summary.commentPlaceholder")}
                fieldSize="md"
              />
            </div>
          </div>

          <Button
            size="sm"
            onClick={() => onSaveGrade(student.student_id)}
            disabled={saving}
          >
            <Save className="mr-1.5 h-3.5 w-3.5" strokeWidth={1.75} />
            {saving ? t("gradebook.summary.savingManual") : t("gradebook.summary.saveManual")}
          </Button>
        </div>
      )}
    </div>
  )
})

function BreakdownEntry({
  label,
  pct,
  weight,
  weighted,
}: {
  label: string
  pct: number
  weight: number
  weighted: number
}) {
  return (
    <div>
      <span className="text-ink-muted">{label}</span>{" "}
      <span className="font-medium">{pct.toFixed(1)}%</span>
      <span className="text-ink-muted text-xs ml-1">
        (×{weight}% = {weighted.toFixed(1)})
      </span>
    </div>
  )
}

function ClassAverageRow({
  summary,
  studentCount,
  classAvg,
}: {
  summary: GradeSummaryResponse
  studentCount: number
  classAvg: number | null
}) {
  const { t } = useTranslation()
  // `classAvg === null` means the backend had nothing to average: a course
  // with no graded work, or one where marking has not started. The per-student
  // rows already show dashes there — printing "0.0%" in bold underneath them
  // would contradict the whole table.
  const hasNumbers = classAvg !== null
  // Category averages exist in `zero_weighted` too — the marks are real, they
  // just carry no weight. Dashing them out here while every student row above
  // shows a figure is the same "dash over marks that exist" defect, one line
  // lower.
  const hasCategoryFigures =
    hasNumbers || summary.students[0]?.breakdown.result_state === "zero_weighted"
  const avg = (pick: (s: StudentCalculatedGrade) => number) =>
    summary.students.reduce((acc, st) => acc + pick(st), 0) / studentCount

  return (
    <div className="grid grid-cols-[1fr_80px_80px_80px_70px_70px] gap-3 px-4 py-3 bg-muted/40 font-semibold text-sm items-center border-t-2">
      <span className="pl-6">{t("gradebook.summary.classAverageRow", { count: studentCount })}</span>
      <p className="tabular-nums text-right">
        {hasCategoryFigures ? `${avg((s) => s.breakdown.quiz_avg).toFixed(1)}%` : "—"}
      </p>
      <p className="tabular-nums text-right">
        {hasCategoryFigures ? `${avg((s) => s.breakdown.assignment_avg).toFixed(1)}%` : "—"}
      </p>
      <p className="tabular-nums text-right">{hasNumbers ? `${classAvg.toFixed(1)}%` : "—"}</p>
      <span />
      <span />
    </div>
  )
}
