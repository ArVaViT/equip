import { Fragment, useMemo } from "react"
import { useTranslation } from "react-i18next"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  BookOpen, Users, Circle, CheckCircle2,
  ChevronDown, ChevronRight, Award, MessageSquare, Save,
} from "lucide-react"
import type { StudentGrade } from "@/types"
import type {
  ChapterInfo,
  ModuleInfo,
  ProgressResponse,
  StudentProgressData,
  GradeForm,
} from "./types"
import { letterColor, chapterTypeIcon } from "./helpers"

interface Props {
  progressData: ProgressResponse | null
  orderedModules: ModuleInfo[]
  moduleChapterMap: Map<string, ChapterInfo[]>
  studentChapterMap: Map<string, Map<string, ChapterInfo>>
  tableStudents: StudentProgressData[]
  manualGrades: Map<string, StudentGrade>
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
  manualGrades,
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
        <CardContent className="py-12 text-center">
          <BookOpen className="h-10 w-10 text-muted-foreground/30 mx-auto mb-3" />
          <p className="text-sm text-muted-foreground">{t("gradebook.failedLoad")}</p>
        </CardContent>
      </Card>
    )
  }

  if (tableStudents.length === 0) {
    return (
      <Card>
        <CardContent className="py-12 text-center">
          <Users className="h-10 w-10 text-muted-foreground/30 mx-auto mb-3" />
          <p className="text-sm text-muted-foreground">{t("gradebook.summary.empty")}</p>
        </CardContent>
      </Card>
    )
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">{t("gradebook.table.title")}</CardTitle>
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
                    manualGrade={manualGrades.get(student.id)}
                    form={forms.get(student.id) ?? { grade: "", comment: "" }}
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

function GradeTableHead({
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
        <th className="sticky left-0 z-10 bg-card border-b border-r px-3 py-2 text-left font-semibold text-sm w-44 min-w-[11rem]">
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
        <th className="border-b px-2 py-2 text-center font-semibold bg-muted/40 w-20">
          {t("gradebook.table.thTotal")}
        </th>
      </tr>
      <tr>
        <th className="sticky left-0 z-10 bg-card border-b border-r" />
        {allChapters.map((ch) => (
          <th
            key={ch.id}
            className="border-b border-r px-1 py-1.5 text-center font-normal text-muted-foreground bg-muted/20 w-16"
            title={ch.title}
          >
            <div className="flex flex-col items-center gap-0.5">
              <span className="text-muted-foreground">{chapterTypeIcon(ch.chapter_type)}</span>
              <span className="truncate max-w-[52px] text-[10px]">{ch.title}</span>
            </div>
          </th>
        ))}
        <th className="border-b px-1 py-1.5 bg-muted/20" />
      </tr>
    </thead>
  )
}

interface GradeTableRowProps {
  student: StudentProgressData
  allChapters: ChapterInfo[]
  studentChapterMap: Map<string, Map<string, ChapterInfo>>
  manualGrade: StudentGrade | undefined
  form: GradeForm
  expanded: boolean
  saving: boolean
  onToggleExpand: (userId: string) => void
  onUpdateForm: (userId: string, field: keyof GradeForm, value: string) => void
  onSaveGrade: (userId: string) => void
}

function GradeTableRow({
  student,
  allChapters,
  studentChapterMap,
  manualGrade,
  form,
  expanded,
  saving,
  onToggleExpand,
  onUpdateForm,
  onSaveGrade,
}: GradeTableRowProps) {
  const { t } = useTranslation()
  const chMap = studentChapterMap.get(student.id)
  const { earned, total } = computeStudentTotals(allChapters, chMap)

  return (
    <Fragment>
      <tr
        className="hover:bg-muted/20 cursor-pointer transition-colors"
        onClick={() => onToggleExpand(student.id)}
      >
        <td className="sticky left-0 z-10 bg-card border-b border-r px-3 py-2 font-medium">
          <div className="flex items-center gap-1.5 min-w-0">
            {expanded ? (
              <ChevronDown className="h-3.5 w-3.5 shrink-0 text-muted-foreground" strokeWidth={1.75} />
            ) : (
              <ChevronRight className="h-3.5 w-3.5 shrink-0 text-muted-foreground" strokeWidth={1.75} />
            )}
            <div className="min-w-0">
              <p className="truncate text-xs font-semibold max-w-[140px]">
                {student.full_name || student.email}
              </p>
              <p className="truncate text-[10px] text-muted-foreground max-w-[140px]">
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
            <span className="font-semibold text-sm">{earned}</span>
            <span className="text-[10px] text-muted-foreground">/{total}</span>
            {manualGrade?.grade && (
              <span
                className={`mt-0.5 rounded-full px-1.5 py-0.5 text-[10px] font-bold ${letterColor(
                  manualGrade.grade,
                )}`}
              >
                {manualGrade.grade}
              </span>
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
}

/**
 * Chapter-type specific status cell: quiz score, assignment state, or a
 * completion marker for reading/video chapters.
 */
function ChapterCell({ chapter }: { chapter: ChapterInfo | undefined }) {
  const { t } = useTranslation()
  if (!chapter) {
    return (
      <div className="flex items-center justify-center h-9 rounded bg-muted/30 text-muted-foreground/40 text-xs">
        —
      </div>
    )
  }

  const type = chapter.chapter_type

  if (type === "quiz" || type === "exam") {
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
          <span className="text-[10px] opacity-70">
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
              <span className="text-[10px] opacity-70">{t("gradebook.table.cellGraded")}</span>
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
    <div className="flex items-center justify-center h-9 rounded bg-muted/20 text-muted-foreground/30 text-[10px]">
      —
    </div>
  )
}

function EmptyCell() {
  return (
    <div className="flex items-center justify-center h-9 rounded bg-muted/30 text-muted-foreground/50 text-xs">
      <Circle className="h-3.5 w-3.5" />
    </div>
  )
}

/**
 * Compute total points earned / available for a student across the given
 * chapter list.
 *
 * - Quiz / exam chapters: use the student's quiz score & max_score; count
 *   max_score as 1 placeholder if the quiz has not been attempted.
 * - Assignment chapters: always count `max_score ?? 100` as available;
 *   add the grade to earned when the assignment has been graded.
 * - Everything else (reading, video, audio): 1 point for completion.
 */
function computeStudentTotals(
  chapters: ChapterInfo[],
  chMap: Map<string, ChapterInfo> | undefined,
): { earned: number; total: number } {
  let earned = 0
  let total = 0
  for (const ch of chapters) {
    const type = ch.chapter_type
    if (type === "quiz" || type === "exam") {
      const qr = chMap?.get(ch.id)?.quiz_result
      if (qr) {
        earned += qr.score
        total += qr.max_score
      } else {
        total += 1
      }
    } else if (type === "assignment") {
      const ar = chMap?.get(ch.id)?.assignment_result
      const maxPts = ar?.max_score ?? 100
      total += maxPts
      if (ar?.grade !== null && ar?.grade !== undefined) {
        earned += ar.grade
      }
    } else {
      total += 1
      if (chMap?.get(ch.id)?.completed) earned += 1
    }
  }
  return { earned, total }
}

function GradeTableLegend() {
  const { t } = useTranslation()
  return (
    <div className="mt-4 flex flex-wrap gap-4 border-t pt-4 text-xs text-muted-foreground">
      <div className="flex items-center gap-1.5">
        <div className="flex h-4 w-4 items-center justify-center rounded border border-success/30 bg-success/10">
          <CheckCircle2 className="h-2.5 w-2.5 text-success" />
        </div>
        {t("gradebook.table.legend.completed")}
      </div>
      <div className="flex items-center gap-1.5">
        <div className="flex h-4 w-6 items-center justify-center rounded border border-success/30 bg-success/10 text-[9px] font-semibold text-success">
          85%
        </div>
        {t("gradebook.table.legend.quizPassed")}
      </div>
      <div className="flex items-center gap-1.5">
        <div className="flex h-4 w-6 items-center justify-center rounded border border-destructive/30 bg-destructive/10 text-[9px] font-semibold text-destructive">
          40%
        </div>
        {t("gradebook.table.legend.quizFailed")}
      </div>
      <div className="flex items-center gap-1.5">
        <div className="flex h-4 w-10 items-center justify-center rounded border border-info/30 bg-info/10 text-[9px] font-semibold text-info">
          {t("gradebook.table.cellGraded")}
        </div>
        {t("gradebook.table.legend.assignmentGraded")}
      </div>
      <div className="flex items-center gap-1.5">
        <div className="flex h-4 w-14 items-center justify-center rounded border border-warning/30 bg-warning/10 text-[9px] text-warning">
          {t("gradebook.table.cellSubmitted")}
        </div>
        {t("gradebook.table.legend.assignmentSubmitted")}
      </div>
      <div className="flex items-center gap-1.5">
        <div className="flex h-4 w-4 items-center justify-center rounded border bg-muted/30">
          <Circle className="h-2.5 w-2.5 text-muted-foreground/40" />
        </div>
        {t("gradebook.table.legend.notSubmitted")}
      </div>
    </div>
  )
}
