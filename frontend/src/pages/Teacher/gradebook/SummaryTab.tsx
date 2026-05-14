import { useMemo } from "react"
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
  GradingConfig,
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
import { letterColor } from "./helpers"

interface Props {
  summary: GradeSummaryResponse | null
  config: GradingConfig
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
 * "Summary Grades" tab: auto-calculated quiz/assignment/participation
 * breakdown per student with an inline panel for manual grade overrides.
 */
export function SummaryTab({
  summary,
  config,
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
        case "participation":
          cmp = a.breakdown.participation_pct - b.breakdown.participation_pct
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
  const classAvg = summary?.class_average ?? 0

  const toggleSort = (field: SortField) => {
    if (sortField === field) {
      onSortChange(field, sortDir === "asc" ? "desc" : "asc")
    } else {
      onSortChange(field, field === "name" ? "asc" : "desc")
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("gradebook.summary.title")}</CardTitle>
        <CardDescription>{t("gradebook.summary.description")}</CardDescription>
      </CardHeader>
      <CardContent>
        {studentCount === 0 ? (
          <EmptyState
            variant="compact"
            icon={<Users strokeWidth={1.75} aria-hidden />}
            title={t("gradebook.summary.empty")}
          />
        ) : (
          <div className="overflow-x-auto">
            <div className="grid grid-cols-[1fr_80px_80px_90px_80px_70px_70px] gap-3 px-4 py-3 border-b bg-muted/30 rounded-t-lg min-w-[700px]">
              <SortHeader field="name" label={t("gradebook.summary.thStudent")} sortField={sortField} sortDir={sortDir} onToggle={toggleSort} />
              <SortHeader field="quiz" label={t("gradebook.summary.thQuiz")} sortField={sortField} sortDir={sortDir} onToggle={toggleSort} className="justify-end" />
              <SortHeader field="assignment" label={t("gradebook.summary.thAssignment")} sortField={sortField} sortDir={sortDir} onToggle={toggleSort} className="justify-end" />
              <SortHeader field="participation" label={t("gradebook.summary.thParticipation")} sortField={sortField} sortDir={sortDir} onToggle={toggleSort} className="justify-end" />
              <SortHeader field="final" label={t("gradebook.summary.thFinal")} sortField={sortField} sortDir={sortDir} onToggle={toggleSort} className="justify-end" />
              <SortHeader field="letter" label={t("gradebook.summary.thGrade")} sortField={sortField} sortDir={sortDir} onToggle={toggleSort} className="justify-center" />
              <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground text-center">{t("gradebook.summary.thManual")}</span>
            </div>

            <div className="divide-y min-w-[700px]">
              {sortedStudents.map((student) => (
                <StudentSummaryRow
                  key={student.student_id}
                  student={student}
                  config={config}
                  manualGrade={manualGrades.get(student.student_id)}
                  form={forms.get(student.student_id) ?? { grade: "", comment: "" }}
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
      className={`flex items-center gap-1 text-xs font-semibold uppercase tracking-wider text-muted-foreground hover:text-foreground transition-colors ${
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
  config: GradingConfig
  manualGrade: StudentGrade | undefined
  form: GradeForm
  expanded: boolean
  saving: boolean
  onToggleExpand: (userId: string) => void
  onUpdateForm: (userId: string, field: keyof GradeForm, value: string) => void
  onSaveGrade: (userId: string) => void
}

function StudentSummaryRow({
  student,
  config,
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
  const hasDifferentManual = Boolean(manualGrade?.grade && manualGrade.grade !== b.letter_grade)

  return (
    <div>
      <div
        className="grid grid-cols-[1fr_80px_80px_90px_80px_70px_70px] gap-3 px-4 py-3 cursor-pointer hover:bg-muted/30 transition-colors items-center"
        onClick={() => onToggleExpand(student.student_id)}
      >
        <div className="flex items-center gap-2 min-w-0">
          {expanded ? (
            <ChevronDown className="h-3.5 w-3.5 shrink-0 text-muted-foreground" strokeWidth={1.75} />
          ) : (
            <ChevronRight className="h-3.5 w-3.5 shrink-0 text-muted-foreground" strokeWidth={1.75} />
          )}
          <div className="min-w-0">
            <p className="text-sm font-medium truncate">{student.student_name || t("gradebook.summary.unknownStudent")}</p>
            <p className="text-xs text-muted-foreground truncate">{student.student_email}</p>
          </div>
        </div>
        <p className="text-sm tabular-nums text-right">{b.quiz_avg.toFixed(1)}%</p>
        <p className="text-sm tabular-nums text-right">{b.assignment_avg.toFixed(1)}%</p>
        <p className="text-sm tabular-nums text-right">{b.participation_pct.toFixed(1)}%</p>
        <p className="text-sm font-semibold tabular-nums text-right">{b.final_score.toFixed(1)}%</p>
        <div className="flex justify-center">
          <span className={`inline-flex items-center justify-center rounded-full px-2.5 py-0.5 text-xs font-bold ${letterColor(b.letter_grade)}`}>
            {b.letter_grade}
          </span>
        </div>
        <div className="flex justify-center">
          {manualGrade?.grade ? (
            <span
              className={`inline-flex items-center justify-center rounded-full px-2.5 py-0.5 text-xs font-bold ${
                hasDifferentManual
                  ? "bg-warning/15 text-warning ring-1 ring-warning/30"
                  : "bg-muted text-muted-foreground"
              }`}
            >
              {manualGrade.grade}
            </span>
          ) : (
            <span className="text-xs text-muted-foreground">—</span>
          )}
        </div>
      </div>

      {expanded && (
        <div className="border-t px-4 py-4 bg-muted/10 space-y-4">
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-x-6 gap-y-2 text-sm">
            <BreakdownEntry
              label={t("gradebook.summary.breakdownQuiz")}
              pct={b.quiz_avg}
              weight={config.quiz_weight}
              weighted={b.quiz_weighted}
            />
            <BreakdownEntry
              label={t("gradebook.summary.breakdownAssignment")}
              pct={b.assignment_avg}
              weight={config.assignment_weight}
              weighted={b.assignment_weighted}
            />
            <BreakdownEntry
              label={t("gradebook.summary.breakdownParticipation")}
              pct={b.participation_pct}
              weight={config.participation_weight}
              weighted={b.participation_weighted}
            />
          </div>

          {hasDifferentManual && (
            <div className="rounded border border-border border-l-[3px] border-l-warning bg-warning/10 px-3 py-2 text-xs text-foreground">
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
}

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
      <span className="text-muted-foreground">{label}</span>{" "}
      <span className="font-medium">{pct.toFixed(1)}%</span>
      <span className="text-muted-foreground text-xs ml-1">
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
  classAvg: number
}) {
  const { t } = useTranslation()
  const avg = (pick: (s: StudentCalculatedGrade) => number) =>
    summary.students.reduce((acc, st) => acc + pick(st), 0) / studentCount

  return (
    <div className="grid grid-cols-[1fr_80px_80px_90px_80px_70px_70px] gap-3 px-4 py-3 bg-muted/40 font-semibold text-sm items-center border-t-2">
      <span className="pl-6">{t("gradebook.summary.classAverageRow", { count: studentCount })}</span>
      <p className="tabular-nums text-right">{avg((s) => s.breakdown.quiz_avg).toFixed(1)}%</p>
      <p className="tabular-nums text-right">{avg((s) => s.breakdown.assignment_avg).toFixed(1)}%</p>
      <p className="tabular-nums text-right">{avg((s) => s.breakdown.participation_pct).toFixed(1)}%</p>
      <p className="tabular-nums text-right">{classAvg.toFixed(1)}%</p>
      <span />
      <span />
    </div>
  )
}
