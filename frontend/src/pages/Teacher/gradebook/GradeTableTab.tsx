import { Fragment, memo, useMemo } from "react"
import { useTranslation } from "react-i18next"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { EmptyState } from "@/components/patterns"
import {
  BookOpen, Users, Circle, CheckCircle2,
  ChevronDown, ChevronRight, Award, MessageSquare, Save, Clock,
} from "lucide-react"
import type { StudentCalculatedGrade } from "@/types"
import type {
  ChapterInfo,
  ModuleInfo,
  ProgressResponse,
  StudentProgressData,
  GradeForm,
} from "./types"
import { EMPTY_FORM, chapterTypeIcon } from "./helpers"
import { officialColumn, type OfficialCell } from "./officialColumn"

interface Props {
  progressData: ProgressResponse | null
  orderedModules: ModuleInfo[]
  moduleChapterMap: Map<string, ChapterInfo[]>
  studentChapterMap: Map<string, Map<string, ChapterInfo>>
  tableStudents: StudentProgressData[]
  /** The official grade per student, from the summary endpoint — the same
   *  numbers the Summary tab shows, so the two tabs cannot disagree. */
  summaryByStudent: Map<string, StudentCalculatedGrade>
  forms: Map<string, GradeForm>
  saving: string | null
  expandedId: string | null
  onUpdateForm: (userId: string, field: keyof GradeForm, value: string) => void
  onSaveGrade: (userId: string) => void
  onToggleExpand: (userId: string) => void
}

/**
 * "Grade Table" tab: a dense spreadsheet view where columns are chapters
 * (grouped by module) and rows are students. Clicking a student reveals
 * the manual override form inline.
 */
export function GradeTableTab({
  progressData,
  orderedModules,
  moduleChapterMap,
  studentChapterMap,
  tableStudents,
  summaryByStudent,
  forms,
  saving,
  expandedId,
  onUpdateForm,
  onSaveGrade,
  onToggleExpand,
}: Props) {
  const { t } = useTranslation()
  const allChapters: ChapterInfo[] = useMemo(
    () => orderedModules.flatMap((m) => moduleChapterMap.get(m.id) ?? []),
    [orderedModules, moduleChapterMap],
  )

  if (!progressData) {
    return (
      <Card>
        <CardContent className="py-10">
          <EmptyState
            variant="compact"
            icon={<BookOpen strokeWidth={1.75} aria-hidden />}
            title={t("gradebook.failedLoad")}
          />
        </CardContent>
      </Card>
    )
  }

  if (tableStudents.length === 0) {
    return (
      <Card>
        <CardContent className="py-10">
          <EmptyState
            variant="compact"
            icon={<Users strokeWidth={1.75} aria-hidden />}
            title={t("gradebook.summary.empty")}
          />
        </CardContent>
      </Card>
    )
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="pb-3">
          <CardTitle>{t("gradebook.table.title")}</CardTitle>
          <CardDescription className="text-xs">{t("gradebook.table.description")}</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table
              className="w-full border-collapse text-xs"
              style={{ minWidth: `${180 + allChapters.length * 64 + 100}px` }}
            >
              <GradeTableHead orderedModules={orderedModules} moduleChapterMap={moduleChapterMap} allChapters={allChapters} />
              <tbody>
                {tableStudents.map((student) => (
                  <GradeTableRow
                    key={student.id}
                    student={student}
                    allChapters={allChapters}
                    studentChapterMap={studentChapterMap}
                    official={officialColumn(summaryByStudent.get(student.id))}
                    form={forms.get(student.id) ?? EMPTY_FORM}
                    expanded={expandedId === student.id}
                    saving={saving === student.id}
                    onToggleExpand={onToggleExpand}
                    onUpdateForm={onUpdateForm}
                    onSaveGrade={onSaveGrade}
                  />
                ))}
              </tbody>
            </table>
          </div>
          <GradeTableLegend />
        </CardContent>
      </Card>
    </div>
  )
}

// Sticky student-column shadow that hints "this column is pinned" even when
// the user hasn't scrolled yet. ``inset-y-0 right-0 -mr-px w-2`` paints a
// 2-px wide gradient strip on the column's right edge; soft enough to fade
// into the table border when stationary, strong enough to read as depth
// when content scrolls underneath.
const STICKY_COL_SHADOW =
  "after:pointer-events-none after:absolute after:inset-y-0 after:right-0 after:w-2 after:-mr-2 after:bg-gradient-to-r after:from-foreground/[0.06] after:to-transparent"

const GradeTableHead = memo(function GradeTableHead({
  orderedModules,
  moduleChapterMap,
  allChapters,
}: {
  orderedModules: ModuleInfo[]
  moduleChapterMap: Map<string, ChapterInfo[]>
  allChapters: ChapterInfo[]
}) {
  const { t } = useTranslation()
  return (
    <thead>
      <tr>
        <th
          className={`sticky left-0 z-10 bg-muted/40 border-b border-r px-3 py-2 text-left font-semibold text-sm w-44 min-w-[11rem] relative ${STICKY_COL_SHADOW}`}
        >
          {t("gradebook.table.thStudent")}
        </th>
        {orderedModules.map((mod) => {
          const modChapters = moduleChapterMap.get(mod.id) ?? []
          if (modChapters.length === 0) return null
          return (
            <th
              key={mod.id}
              colSpan={modChapters.length}
              className="border-b border-r px-2 py-2 text-center font-semibold bg-muted/40 truncate max-w-[200px]"
            >
              {mod.title}
            </th>
          )
        })}
        <th className="border-b border-r px-2 py-2 text-center font-semibold bg-muted/40 w-20">
          {t("gradebook.table.thTotal")}
        </th>
      </tr>
      <tr>
        <th
          className={`sticky left-0 z-10 bg-muted/20 border-b border-r relative ${STICKY_COL_SHADOW}`}
          aria-hidden
        />
        {allChapters.map((ch) => (
          <th
            key={ch.id}
            className="border-b border-r px-1 py-1.5 text-center font-normal text-ink-muted bg-muted/20 w-16"
            title={ch.title}
          >
            <div className="flex flex-col items-center gap-0.5">
              <span className="text-ink-muted">{chapterTypeIcon(ch.chapter_type)}</span>
              <span className="truncate max-w-[52px] text-xs">{ch.title}</span>
            </div>
          </th>
        ))}
        <th className="border-b border-r px-1 py-1.5 bg-muted/20" aria-hidden />
      </tr>
    </thead>
  )
})

interface GradeTableRowProps {
  student: StudentProgressData
  allChapters: ChapterInfo[]
  studentChapterMap: Map<string, Map<string, ChapterInfo>>
  official: OfficialCell
  form: GradeForm
  expanded: boolean
  saving: boolean
  onToggleExpand: (userId: string) => void
  onUpdateForm: (userId: string, field: keyof GradeForm, value: string) => void
  onSaveGrade: (userId: string) => void
}

/**
 * One spreadsheet row per student. Memoised so typing in one row's
 * override-grade form (which is parent state) doesn't rerender every
 * other row. The row's `studentChapterMap` is the full course-wide map
 * intentionally — its identity is stable across renders because it lives
 * in a `useMemo` in `TeacherGradebook`, so referential equality holds.
 */
const GradeTableRow = memo(function GradeTableRow({
  student,
  allChapters,
  studentChapterMap,
  official,
  form,
  expanded,
  saving,
  onToggleExpand,
  onUpdateForm,
  onSaveGrade,
}: GradeTableRowProps) {
  const { t } = useTranslation()
  const chMap = studentChapterMap.get(student.id)

  return (
    <Fragment>
      <tr
        className="group cursor-pointer transition-colors hover:bg-muted/40"
        onClick={() => onToggleExpand(student.id)}
      >
        <td
          className={`sticky left-0 z-10 bg-card group-hover:bg-muted/40 border-b border-r px-3 py-2 font-medium relative transition-colors ${STICKY_COL_SHADOW}`}
        >
          <div className="flex items-center gap-1.5 min-w-0">
            {expanded ? (
              <ChevronDown className="h-3.5 w-3.5 shrink-0 text-ink-muted" strokeWidth={1.75} />
            ) : (
              <ChevronRight className="h-3.5 w-3.5 shrink-0 text-ink-muted" strokeWidth={1.75} />
            )}
            <div className="min-w-0">
              <p className="truncate text-xs font-semibold max-w-[140px]">
                {student.full_name || student.email}
              </p>
              <p className="truncate text-xs text-ink-muted max-w-[140px]">
                {student.email}
              </p>
            </div>
          </div>
        </td>
        {allChapters.map((ch) => (
          <td
            key={ch.id}
            className="border-b border-r px-1 py-1"
            onClick={(e) => e.stopPropagation()}
          >
            <ChapterCell chapter={chMap?.get(ch.id)} />
          </td>
        ))}
        <td className="border-b px-2 py-2 text-center">
          <div className="flex flex-col items-center">
            {/* The official grade, the same one the Summary tab and the CSV
                show. This column used to add up raw points, and that sum could
                disagree with the Summary tab two clicks away. */}
            <span className="font-semibold text-sm">
              {official.text ?? "—"}
            </span>
            {official.isManual && (
              <span className="text-[10px] font-medium text-info">
                {t("gradebook.table.setByTeacher")}
              </span>
            )}
            {official.noteKey && (
              <span className="text-[10px] text-ink-muted leading-tight">{t(official.noteKey)}</span>
            )}
          </div>
        </td>
      </tr>
      {expanded && (
        <tr>
          <td colSpan={allChapters.length + 2} className="bg-muted/10 border-b px-4 py-3">
            <div className="flex flex-wrap items-end gap-3">
              <div className="space-y-1">
                <label className="flex items-center gap-1 text-xs font-medium">
                  <Award className="h-3.5 w-3.5" strokeWidth={1.75} /> {t("gradebook.table.overrideGrade")}
                </label>
                <Input
                  value={form.grade}
                  onChange={(e) => onUpdateForm(student.id, "grade", e.target.value)}
                  placeholder={t("gradebook.table.overridePlaceholder")}
                  fieldSize="sm"
                  className="w-28"
                />
              </div>
              <div className="space-y-1 flex-1 min-w-[180px]">
                <label className="flex items-center gap-1 text-xs font-medium">
                  <MessageSquare className="h-3.5 w-3.5" strokeWidth={1.75} /> {t("gradebook.table.comment")}
                </label>
                <Input
                  value={form.comment}
                  onChange={(e) => onUpdateForm(student.id, "comment", e.target.value)}
                  placeholder={t("gradebook.table.commentPlaceholder")}
                  fieldSize="sm"
                  className="min-w-0 flex-1"
                />
              </div>
              <Button
                size="sm"
                className="h-8 text-xs"
                onClick={() => onSaveGrade(student.id)}
                disabled={saving}
              >
                <Save className="mr-1 h-3.5 w-3.5" strokeWidth={1.75} />
                {saving ? t("gradebook.table.saving") : t("gradebook.table.saveGrade")}
              </Button>
            </div>
          </td>
        </tr>
      )}
    </Fragment>
  )
})

/**
 * Chapter-type specific status cell: quiz score, assignment state, or a
 * completion marker for reading/video chapters.
 */
function ChapterCell({ chapter }: { chapter: ChapterInfo | undefined }) {
  const { t } = useTranslation()
  if (!chapter) {
    return (
      <div className="flex items-center justify-center h-9 rounded bg-muted/30 text-ink-muted/40 text-xs">
        —
      </div>
    )
  }

  const type = chapter.chapter_type

  if (type === "quiz" || type === "exam") {
    if (chapter.quiz_result?.awaiting_grading) {
      // An essay quiz is submitted long before it is marked. Until a teacher
      // reads the open answers its score is 0 out of the full total, and the
      // ordinary renderer paints that a red 0% — a failure shown for work
      // nobody has looked at, on the screen that decides certificates.
      return (
        <div
          className="flex h-9 flex-col items-center justify-center rounded border border-warning/30 bg-warning/10 px-1 text-xs font-medium text-warning"
          title={t("gradebook.table.awaitingGradingTitle")}
        >
          <Clock className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
        </div>
      )
    }
    if (chapter.quiz_result) {
      const pct =
        chapter.quiz_result.max_score > 0
          ? Math.round((chapter.quiz_result.score / chapter.quiz_result.max_score) * 100)
          : 0
      return (
        <div
          className={`flex h-9 flex-col items-center justify-center rounded border px-1 text-xs font-medium ${
            chapter.quiz_result.passed
              ? "border-success/30 bg-success/10 text-success"
              : "border-destructive/30 bg-destructive/10 text-destructive"
          }`}
        >
          <span className="font-semibold">{pct}%</span>
          <span className="text-xs opacity-70">
            {chapter.quiz_result.score}/{chapter.quiz_result.max_score}
          </span>
        </div>
      )
    }
    return <EmptyCell />
  }

  if (type === "assignment") {
    if (chapter.assignment_result) {
      const graded = chapter.assignment_result.grade !== null
      return (
        <div
          className={`flex h-9 flex-col items-center justify-center rounded border px-1 text-xs font-medium ${
            graded
              ? "border-info/30 bg-info/10 text-info"
              : "border-warning/30 bg-warning/10 text-warning"
          }`}
        >
          {graded ? (
            <>
              <span className="font-semibold">{chapter.assignment_result.grade}pt</span>
              <span className="text-xs opacity-70">{t("gradebook.table.cellGraded")}</span>
            </>
          ) : (
            <span>{t("gradebook.table.cellSubmitted")}</span>
          )}
        </div>
      )
    }
    return <EmptyCell />
  }

  return (
    <div className="flex items-center justify-center h-9 rounded bg-muted/20 text-ink-muted/30 text-xs">
      —
    </div>
  )
}

function EmptyCell() {
  return (
    <div className="flex items-center justify-center h-9 rounded bg-muted/30 text-ink-muted/50 text-xs">
      <Circle className="h-3.5 w-3.5" strokeWidth={1.75} />
    </div>
  )
}

function GradeTableLegend() {
  const { t } = useTranslation()
  return (
    <div className="mt-4 flex flex-wrap gap-4 border-t pt-4 text-xs text-ink-muted">
      <div className="flex items-center gap-1.5">
        <div className="flex h-5 w-5 items-center justify-center rounded border border-success/30 bg-success/10">
          <CheckCircle2 className="h-3 w-3 text-success" strokeWidth={1.75} />
        </div>
        {t("gradebook.table.legend.completed")}
      </div>
      <div className="flex items-center gap-1.5">
        <div className="flex h-5 w-9 items-center justify-center rounded border border-success/30 bg-success/10 text-xs font-semibold text-success">
          85%
        </div>
        {t("gradebook.table.legend.quizPassed")}
      </div>
      <div className="flex items-center gap-1.5">
        <div className="flex h-5 w-9 items-center justify-center rounded border border-destructive/30 bg-destructive/10 text-xs font-semibold text-destructive">
          40%
        </div>
        {t("gradebook.table.legend.quizFailed")}
      </div>
      <div className="flex items-center gap-1.5">
        <div className="flex h-5 items-center justify-center rounded border border-info/30 bg-info/10 px-1.5 text-xs font-semibold text-info">
          {t("gradebook.table.cellGraded")}
        </div>
        {t("gradebook.table.legend.assignmentGraded")}
      </div>
      <div className="flex items-center gap-1.5">
        <div className="flex h-5 items-center justify-center rounded border border-warning/30 bg-warning/10 px-1.5 text-xs text-warning">
          {t("gradebook.table.cellSubmitted")}
        </div>
        {t("gradebook.table.legend.assignmentSubmitted")}
      </div>
      <div className="flex items-center gap-1.5">
        <div className="flex h-5 w-5 items-center justify-center rounded border bg-muted/30">
          <Circle className="h-3 w-3 text-ink-muted/40" strokeWidth={1.75} />
        </div>
        {t("gradebook.table.legend.notSubmitted")}
      </div>
    </div>
  )
}
