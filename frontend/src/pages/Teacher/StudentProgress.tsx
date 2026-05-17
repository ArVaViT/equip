import { useCallback, useEffect, useMemo, useState } from "react"
import { Link, useParams } from "react-router-dom"
import { useTranslation } from "react-i18next"
import { useDebouncedSearchParam } from "@/hooks/useDebouncedSearchParam"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { coursesService } from "@/services/courses"
import { toast } from "@/lib/toast"
import { getErrorDetail } from "@/lib/errorDetail"
import type { StudentProgressResponse } from "@/types"
import {
  ArrowLeft,
  BarChart3,
  ChevronRight,
  ClipboardList,
  Search,
  Users,
} from "lucide-react"
import { ErrorState } from "@/components/patterns"
import {
  averageProgress,
  completionRate,
  ProgressStats,
  StudentProgressSkeleton,
  StudentTable,
  type SortColumn,
  type SortDirection,
} from "./progress"

/**
 * Teacher view of every enrolled student in a course. Owns the fetch,
 * filter, and sort state; delegates presentation to `progress/*`.
 *
 * The table itself stays here as a single derived memo so we can keep
 * sort/search centralised — each row only knows about its own expansion
 * and mutation calls.
 */
export default function StudentProgress() {
  const { courseId } = useParams<{ courseId: string }>()
  const { t } = useTranslation()
  const {
    input: searchInput,
    setInput: setSearchInput,
    value: search,
    maxLength,
  } = useDebouncedSearchParam()

  const [data, setData] = useState<StudentProgressResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [sortBy, setSortBy] = useState<SortColumn>("name")
  const [sortDir, setSortDir] = useState<SortDirection>("asc")

  const load = useCallback(
    async (signal?: { cancelled: boolean }) => {
      if (!courseId) return
      setLoading(true)
      setData(null)
      try {
        const result = await coursesService.getStudentProgress(courseId)
        if (signal?.cancelled) return
        setData(result)
      } catch (err) {
        if (signal?.cancelled) return
        toast({
          title: getErrorDetail(err, t("studentProgress.loadFailed")),
          variant: "destructive",
        })
      } finally {
        if (!signal?.cancelled) setLoading(false)
      }
    },
    [courseId, t],
  )

  useEffect(() => {
    const signal = { cancelled: false }
    void load(signal)
    return () => {
      signal.cancelled = true
    }
  }, [load])

  const toggleSort = (col: SortColumn) => {
    if (sortBy === col) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"))
    } else {
      setSortBy(col)
      setSortDir("asc")
    }
  }

  const filtered = useMemo(() => {
    if (!data) return []
    const q = search.trim().toLowerCase()
    const list = q
      ? data.students.filter(
          (s) =>
            (s.full_name ?? "").toLowerCase().includes(q) ||
            (s.email ?? "").toLowerCase().includes(q),
        )
      : data.students
    return [...list].sort((a, b) => {
      const dir = sortDir === "asc" ? 1 : -1
      if (sortBy === "name") {
        return (a.full_name ?? "").localeCompare(b.full_name ?? "") * dir
      }
      if (sortBy === "progress") {
        return (a.progress - b.progress) * dir
      }
      const da = a.last_activity ? new Date(a.last_activity).getTime() : 0
      const db = b.last_activity ? new Date(b.last_activity).getTime() : 0
      return (da - db) * dir
    })
  }, [data, search, sortBy, sortDir])

  const handleStudentChapterUpdate = useCallback(
    (
      studentId: string,
      chapterId: string,
      completed: boolean,
      completedBy: "teacher" | "self" | null,
    ) => {
      setData((prev) => {
        if (!prev) return prev
        return {
          ...prev,
          students: prev.students.map((s) => {
            if (s.id !== studentId) return s
            const updatedChapters = s.chapters?.map((ch) =>
              ch.id === chapterId ? { ...ch, completed, completed_by: completedBy } : ch,
            )
            const completedCount =
              updatedChapters?.filter((ch) => ch.completed).length ?? s.chapters_completed
            return {
              ...s,
              chapters: updatedChapters,
              chapters_completed: completed
                ? s.chapters_completed + 1
                : Math.max(0, s.chapters_completed - 1),
              progress:
                prev.total_chapters > 0
                  ? Math.round((completedCount / prev.total_chapters) * 100)
                  : s.progress,
            }
          }),
        }
      })
    },
    [],
  )

  if (loading) return <StudentProgressSkeleton />
  if (!data)
    return (
      <div className="container mx-auto px-4 py-8 max-w-6xl">
        <ErrorState
          icon={<Users strokeWidth={1.75} />}
          title={t("studentProgress.loadFailed")}
          description={t("studentProgress.loadFailedDescription")}
          action={
            <Button variant="outline" onClick={() => load()}>
              {t("studentProgress.retry")}
            </Button>
          }
          secondaryAction={
            <Link to="/teacher">
              <Button variant="ghost">
                <ArrowLeft className="h-4 w-4 mr-1.5" strokeWidth={1.75} />
                {t("studentProgress.backToCourses")}
              </Button>
            </Link>
          }
        />
      </div>
    )

  return (
    <div className="container mx-auto px-4 py-8 max-w-6xl">
      <div className="flex items-center gap-2 text-sm text-muted-foreground mb-6">
        <Link to="/teacher" className="hover:text-foreground transition-colors">
          {t("studentProgress.breadcrumb.myCourses")}
        </Link>
        <ChevronRight className="h-3.5 w-3.5" strokeWidth={1.75} />
        <Link
          to={`/teacher/courses/${courseId}`}
          className="hover:text-foreground transition-colors"
        >
          {data.course_title || t("studentProgress.breadcrumb.courseFallback")}
        </Link>
        <ChevronRight className="h-3.5 w-3.5" strokeWidth={1.75} />
        <span className="text-foreground font-medium">{t("studentProgress.heading")}</span>
      </div>

      <div className="flex items-center gap-3 mb-8">
        <div className="flex-1">
          <h1 className="text-3xl font-serif font-bold tracking-tight">{t("studentProgress.heading")}</h1>
          <p className="text-muted-foreground mt-1">{data.course_title}</p>
        </div>
        <div className="flex items-center gap-2">
          <Link to={`/teacher/courses/${courseId}/analytics`}>
            <Button size="sm" variant="outline">
              <BarChart3 className="h-4 w-4 mr-1.5" strokeWidth={1.75} />
              {t("studentProgress.analytics")}
            </Button>
          </Link>
          <Link to={`/teacher/courses/${courseId}/gradebook`}>
            <Button size="sm" variant="outline">
              <ClipboardList className="h-4 w-4 mr-1.5" strokeWidth={1.75} />
              {t("studentProgress.gradebook")}
            </Button>
          </Link>
        </div>
      </div>

      <ProgressStats
        totalStudents={data.students.length}
        averageProgress={averageProgress(data.students)}
        completionRate={completionRate(data.students)}
      />

      <div className="relative mb-6">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" strokeWidth={1.75} aria-hidden="true" />
        <Input
          placeholder={t("studentProgress.searchPlaceholder")}
          value={searchInput}
          onChange={(e) => setSearchInput(e.target.value.slice(0, maxLength))}
          maxLength={maxLength}
          className="pl-10"
        />
      </div>

      <StudentTable
        students={filtered}
        courseId={courseId ?? ""}
        hasSearch={Boolean(search)}
        expandedId={expandedId}
        onExpandToggle={(id) => setExpandedId((prev) => (prev === id ? null : id))}
        sortBy={sortBy}
        sortDir={sortDir}
        onToggleSort={toggleSort}
        onChapterUpdate={handleStudentChapterUpdate}
      />
    </div>
  )
}
