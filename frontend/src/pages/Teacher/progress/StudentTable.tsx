import { useTranslation } from "react-i18next"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Users } from "lucide-react"
import { EmptyState as DesignEmptyState } from "@/components/patterns/EmptyState"
import { StudentRow } from "./StudentRow"
import {
  type SortColumn,
  type SortDirection,
  type StudentData,
} from "./helpers"

interface Props {
  students: StudentData[]
  courseId: string
  hasSearch: boolean
  expandedId: string | null
  onExpandToggle: (id: string) => void
  sortBy: SortColumn
  sortDir: SortDirection
  onToggleSort: (col: SortColumn) => void
  onChapterUpdate: (
    studentId: string,
    chapterId: string,
    completed: boolean,
    completedBy: "teacher" | "self" | null,
  ) => void
}

export function StudentTable({
  students,
  courseId,
  hasSearch,
  expandedId,
  onExpandToggle,
  sortBy,
  sortDir,
  onToggleSort,
  onChapterUpdate,
}: Props) {
  const { t } = useTranslation()
  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 font-serif text-lg font-semibold tracking-tight">
          <Users className="h-5 w-5" strokeWidth={1.75} aria-hidden />
          {t("studentProgress.table.heading")}
          <span className="text-sm font-normal text-ink-muted">
            ({students.length})
          </span>
        </CardTitle>
        <CardDescription>{t("studentProgress.table.description")}</CardDescription>
      </CardHeader>
      <CardContent>
        {students.length === 0 ? (
          <EmptyState hasSearch={hasSearch} />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left">
                  <th className="pb-3 pr-2 w-8" />
                  <SortableHeader
                    label={t("studentProgress.table.name")}
                    col="name"
                    sortBy={sortBy}
                    sortDir={sortDir}
                    onToggle={onToggleSort}
                  />
                  <th className="pb-3 font-medium text-ink-muted">{t("studentProgress.table.email")}</th>
                  <SortableHeader
                    label={t("studentProgress.table.progress")}
                    col="progress"
                    sortBy={sortBy}
                    sortDir={sortDir}
                    onToggle={onToggleSort}
                  />
                  <th className="pb-3 font-medium text-ink-muted">{t("studentProgress.table.chapters")}</th>
                  <th className="pb-3 font-medium text-ink-muted">{t("studentProgress.table.quizAvg")}</th>
                  <th className="pb-3 font-medium text-ink-muted">{t("studentProgress.table.assignAvg")}</th>
                  <SortableHeader
                    label={t("studentProgress.table.lastActive")}
                    col="last_activity"
                    sortBy={sortBy}
                    sortDir={sortDir}
                    onToggle={onToggleSort}
                  />
                </tr>
              </thead>
              <tbody>
                {students.map((student) => (
                  <StudentRow
                    key={student.id}
                    student={student}
                    isExpanded={expandedId === student.id}
                    onToggle={() => onExpandToggle(student.id)}
                    quizAvg={student.quiz_avg}
                    assignmentAvg={student.assignment_avg}
                    overallGrade={student.overall_grade}
                    courseId={courseId}
                    onChapterUpdate={onChapterUpdate}
                  />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

function EmptyState({ hasSearch }: { hasSearch: boolean }) {
  const { t } = useTranslation()
  return (
    <DesignEmptyState
      variant="compact"
      icon={<Users strokeWidth={1.75} aria-hidden />}
      title={
        hasSearch
          ? t("studentProgress.table.emptyNoMatch")
          : t("studentProgress.table.emptyNoStudents")
      }
    />
  )
}

interface SortableHeaderProps {
  label: string
  col: SortColumn
  sortBy: SortColumn
  sortDir: SortDirection
  onToggle: (col: SortColumn) => void
}

function SortableHeader({ label, col, sortBy, sortDir, onToggle }: SortableHeaderProps) {
  return (
    <th
      className="pb-3 font-medium text-ink-muted cursor-pointer select-none hover:text-ink transition-colors"
      onClick={() => onToggle(col)}
    >
      {label}
      {sortBy === col && <span className="ml-1">{sortDir === "asc" ? "↑" : "↓"}</span>}
    </th>
  )
}
