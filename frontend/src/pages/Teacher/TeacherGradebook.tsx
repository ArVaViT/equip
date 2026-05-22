import { useEffect, useState, useCallback, useMemo, useRef } from "react"
import { useTranslation } from "react-i18next"
import { useParams, useSearchParams, Link } from "react-router-dom"
import { Skeleton } from "@/components/ui/skeleton"
import { Button } from "@/components/ui/button"
import { coursesService } from "@/services/courses"
import type { GradingConfig, GradeSummaryResponse, StudentGrade } from "@/types"
import { toast } from "@/lib/toast"
import { ArrowLeft, Award, ChevronRight, Download } from "lucide-react"
import { ErrorState } from "@/components/patterns"
import {
  SORT_FIELDS,
  TABS,
  type ActiveTab,
  type SortField,
  type SortDir,
  type ChapterInfo,
  type GradeForm,
  type ProgressResponse,
} from "./gradebook/types"
import { GradebookStats } from "./gradebook/GradebookStats"
import { GradebookTabs } from "./gradebook/GradebookTabs"
import { GradingConfigCard } from "./gradebook/GradingConfigCard"
import { SummaryTab } from "./gradebook/SummaryTab"
import { GradeTableTab } from "./gradebook/GradeTableTab"
import { EMPTY_FORM } from "./gradebook/helpers"
import { useUserTour } from "@/hooks/useUserTour"
import { gradebookSteps } from "@/lib/tourSteps"

/**
 * Gradebook page: top-level composition of the summary view, the grade
 * table view, stats, and grading-config card. This component owns all
 * state (config drafts, manual grade forms, expanded row, loaders); the
 * per-tab components are pure, prop-driven render layers.
 */
export default function TeacherGradebook() {
  const { t } = useTranslation()
  const { courseId } = useParams<{ courseId: string }>()
  const [params, setParams] = useSearchParams()

  const activeTab: ActiveTab = (TABS as readonly string[]).includes(params.get("tab") ?? "")
    ? (params.get("tab") as ActiveTab)
    : "summary"
  const sortField: SortField = (SORT_FIELDS as readonly string[]).includes(params.get("sort") ?? "")
    ? (params.get("sort") as SortField)
    : "name"
  const sortDir: SortDir = params.get("dir") === "desc" ? "desc" : "asc"

  const setActiveTab = (next: ActiveTab) =>
    // PUSH (not replace) -- summary ↔ table tab switching is primary
    // navigation; back-button should undo it instead of dropping the
    // user out of the gradebook entirely. Sort toggles below stay on
    // ``replace`` since each column-click is a quick filter tweak,
    // not a navigation step worth back-stop-ing.
    setParams((p) => {
      const n = new URLSearchParams(p)
      if (next === "summary") n.delete("tab")
      else n.set("tab", next)
      return n
    })

  const applySort = (field: SortField, dir: SortDir) =>
    setParams(
      (p) => {
        const n = new URLSearchParams(p)
        if (field === "name") n.delete("sort")
        else n.set("sort", field)
        if (dir === "asc") n.delete("dir")
        else n.set("dir", dir)
        return n
      },
      { replace: true },
    )

  const [courseTitle, setCourseTitle] = useState("")
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [config, setConfig] = useState<GradingConfig>({
    quiz_weight: 30,
    assignment_weight: 50,
    participation_weight: 20,
  })
  const [configDraft, setConfigDraft] = useState<GradingConfig>(config)
  const [configOpen, setConfigOpen] = useState(false)
  const [savingConfig, setSavingConfig] = useState(false)

  const [summary, setSummary] = useState<GradeSummaryResponse | null>(null)
  const [manualGrades, setManualGrades] = useState<Map<string, StudentGrade>>(new Map())
  const [progressData, setProgressData] = useState<ProgressResponse | null>(null)

  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [forms, setForms] = useState<Map<string, GradeForm>>(new Map())
  // Mirror of `forms` so memoised handlers (saveGrade) can read the
  // current draft without taking `forms` as a dependency and busting
  // their stable identity on every keystroke.
  const formsRef = useRef(forms)
  useEffect(() => {
    formsRef.current = forms
  }, [forms])
  const [saving, setSaving] = useState<string | null>(null)
  const [exporting, setExporting] = useState(false)

  const [reloadKey, setReloadKey] = useState(0)
  const reload = useCallback(() => setReloadKey((k) => k + 1), [])

  useUserTour({
    tourId: "gradebook-v1",
    steps: gradebookSteps(t),
    ready: !loading && !error,
  })

  useEffect(() => {
    if (!courseId) return
    let cancelled = false
    setLoading(true)
    setError(null)
    setExpandedId(null)
    ;(async () => {
      try {
        const [course, rawGrades, gradeSummary, progress] = await Promise.all([
          coursesService.getCourse(courseId),
          coursesService.getCourseGrades(courseId).catch(() => []),
          coursesService.getGradeSummary(courseId).catch(() => null),
          coursesService.getStudentProgress(courseId).catch(() => null),
        ])
        if (cancelled) return
        setCourseTitle(course.title)

        const gradeMap = new Map<string, StudentGrade>()
        const formMap = new Map<string, GradeForm>()
        for (const g of rawGrades ?? []) {
          gradeMap.set(g.student_id, g)
          formMap.set(g.student_id, {
            grade: g.grade ?? "",
            comment: g.comment ?? "",
          })
        }
        setManualGrades(gradeMap)
        setForms(formMap)

        if (gradeSummary) {
          setSummary(gradeSummary)
          setConfig(gradeSummary.config)
          setConfigDraft(gradeSummary.config)
        }
        if (progress) {
          setProgressData(progress as ProgressResponse)
        }
      } catch {
        if (!cancelled) setError(t("gradebook.failedLoad"))
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [courseId, reloadKey, t])

  const saveConfig = async () => {
    if (!courseId) return
    const total =
      configDraft.quiz_weight + configDraft.assignment_weight + configDraft.participation_weight
    if (total !== 100) return
    setSavingConfig(true)
    try {
      const updated = await coursesService.updateGradingConfig(courseId, configDraft)
      setConfig(updated)
      toast({ title: t("toast.gradingWeightsSaved"), variant: "success" })
      const gradeSummary = await coursesService.getGradeSummary(courseId)
      setSummary(gradeSummary)
    } catch {
      toast({ title: t("toast.gradingConfigSaveFailed"), variant: "destructive" })
    } finally {
      setSavingConfig(false)
    }
  }

  // Stable identity for the row-level handlers so memoised row components
  // (StudentSummaryRow / GradeTableRow) don't get a fresh prop on every
  // keystroke in any unrelated row's override form.
  const toggleExpand = useCallback((userId: string) => {
    setExpandedId((prev) => {
      if (prev === userId) return null
      // Seed an empty draft for newly-expanded rows so the inputs are
      // controlled from the first render. Skip the setForms call when the
      // entry already exists to avoid an extra render on re-expand.
      setForms((prevForms) => {
        if (prevForms.has(userId)) return prevForms
        return new Map(prevForms).set(userId, EMPTY_FORM)
      })
      return userId
    })
  }, [])

  const updateForm = useCallback(
    (userId: string, field: keyof GradeForm, value: string) => {
      setForms((prev) => {
        const next = new Map(prev)
        const current = next.get(userId) ?? EMPTY_FORM
        next.set(userId, { ...current, [field]: value })
        return next
      })
    },
    [],
  )

  const saveGrade = useCallback(
    async (userId: string) => {
      if (!courseId) return
      setSaving(userId)
      try {
        const form = formsRef.current.get(userId) ?? EMPTY_FORM
        const data = await coursesService.upsertGrade(courseId, userId, {
          grade: form.grade.trim() || undefined,
          comment: form.comment.trim() || undefined,
        })
        setManualGrades((prev) => new Map(prev).set(userId, data))
        toast({ title: t("toast.gradeSaved"), variant: "success" })
      } catch {
        toast({ title: t("toast.gradeSaveFailed"), variant: "destructive" })
      } finally {
        setSaving(null)
      }
    },
    [courseId, t],
  )

  const handleExportCSV = async () => {
    if (!courseId) return
    setExporting(true)
    try {
      const blob = await coursesService.exportGradesCSV(courseId)
      const url = URL.createObjectURL(blob)
      const a = document.createElement("a")
      a.href = url
      const safeTitle = (courseTitle || courseId || "export")
        .replace(/[\\/:*?"<>|]/g, "_")
        .slice(0, 50)
        .trim()
      a.download = `grades_${safeTitle}.csv`
      a.click()
      URL.revokeObjectURL(url)
    } catch {
      toast({ title: t("toast.exportGradesFailed"), variant: "destructive" })
    } finally {
      setExporting(false)
    }
  }

  const moduleChapterMap = useMemo(() => {
    if (!progressData) return new Map<string, ChapterInfo[]>()
    const studentWithChapters = progressData.students[0]
    if (!studentWithChapters) return new Map<string, ChapterInfo[]>()
    const map = new Map<string, ChapterInfo[]>()
    for (const ch of studentWithChapters.chapters) {
      const arr = map.get(ch.module_id) ?? []
      arr.push(ch)
      map.set(ch.module_id, arr)
    }
    return map
  }, [progressData])

  const orderedModules = useMemo(() => {
    if (!progressData) return []
    return [...(progressData.modules ?? [])].sort((a, b) => a.order_index - b.order_index)
  }, [progressData])

  const studentChapterMap = useMemo(() => {
    if (!progressData) return new Map<string, Map<string, ChapterInfo>>()
    const outer = new Map<string, Map<string, ChapterInfo>>()
    for (const student of progressData.students) {
      const inner = new Map<string, ChapterInfo>()
      for (const ch of student.chapters) {
        inner.set(ch.id, ch)
      }
      outer.set(student.id, inner)
    }
    return outer
  }, [progressData])

  const tableStudents = useMemo(() => {
    if (!progressData) return []
    return [...progressData.students].sort((a, b) =>
      (a.full_name ?? "").localeCompare(b.full_name ?? ""),
    )
  }, [progressData])

  if (loading) return <TeacherGradebookSkeleton />

  if (error) {
    return (
      <div className="container mx-auto px-4 py-8 max-w-6xl">
        <ErrorState
          icon={<Award strokeWidth={1.75} aria-hidden />}
          description={error}
          action={
            <Button onClick={reload} size="sm" variant="outline">
              {t("common.tryAgain")}
            </Button>
          }
          secondaryAction={
            <Link to="/teacher">
              <Button size="sm" variant="ghost">
                <ArrowLeft className="mr-1.5 h-4 w-4" strokeWidth={1.75} aria-hidden />
                {t("teacher.backToCourses")}
              </Button>
            </Link>
          }
        />
      </div>
    )
  }

  const studentCount = summary?.students.length ?? 0
  const classAvg = summary?.class_average ?? 0

  return (
    <div className="container mx-auto px-4 py-8 max-w-7xl">
      <div className="flex items-center gap-2 text-sm text-muted-foreground mb-6">
        <Link to="/teacher" className="hover:text-foreground transition-colors">
          {t("gradebook.breadcrumbCourses")}
        </Link>
        <ChevronRight className="h-4 w-4 shrink-0 opacity-70" strokeWidth={1.75} aria-hidden />
        <Link
          to={`/teacher/courses/${courseId}`}
          className="hover:text-foreground transition-colors truncate"
        >
          {courseTitle || t("gradebook.breadcrumbCourseFallback")}
        </Link>
        <ChevronRight className="h-4 w-4 shrink-0 opacity-70" strokeWidth={1.75} aria-hidden />
        <span className="text-foreground font-medium">{t("gradebook.pageHeading")}</span>
      </div>

      <div className="mb-6 flex items-start justify-between gap-4">
        <div>
          <h1 className="flex items-center gap-2 font-serif text-3xl font-bold tracking-tight">
            <Award className="h-6 w-6 shrink-0 text-primary" strokeWidth={1.75} aria-hidden />
            {t("gradebook.pageHeading")}
          </h1>
          {courseTitle && <p className="text-muted-foreground mt-1">{courseTitle}</p>}
        </div>
        {studentCount > 0 && (
          <Button variant="outline" size="sm" onClick={handleExportCSV} disabled={exporting}>
            <Download className="mr-1.5 h-4 w-4" strokeWidth={1.75} aria-hidden />
            {exporting ? t("gradebook.exporting") : t("gradebook.exportCsv")}
          </Button>
        )}
      </div>

      <GradebookStats
        studentCount={studentCount}
        classAverage={classAvg}
        gradedCount={manualGrades.size}
        config={config}
      />

      <GradebookTabs active={activeTab} onChange={setActiveTab} />

      <div data-tour="gradebook-table">
      {activeTab === "summary" && (
        <>
          <GradingConfigCard
            open={configOpen}
            onToggle={() => setConfigOpen(!configOpen)}
            draft={configDraft}
            onDraftChange={setConfigDraft}
            onSave={saveConfig}
            saving={savingConfig}
          />
          <SummaryTab
            summary={summary}
            config={config}
            manualGrades={manualGrades}
            forms={forms}
            saving={saving}
            expandedId={expandedId}
            sortField={sortField}
            sortDir={sortDir}
            onSortChange={applySort}
            onToggleExpand={toggleExpand}
            onUpdateForm={updateForm}
            onSaveGrade={saveGrade}
          />
        </>
      )}

      {activeTab === "table" && (
        <GradeTableTab
          progressData={progressData}
          orderedModules={orderedModules}
          moduleChapterMap={moduleChapterMap}
          studentChapterMap={studentChapterMap}
          tableStudents={tableStudents}
          manualGrades={manualGrades}
          forms={forms}
          saving={saving}
          expandedId={expandedId}
          onUpdateForm={updateForm}
          onSaveGrade={saveGrade}
          onToggleExpand={toggleExpand}
        />
      )}
      </div>
    </div>
  )
}

/**
 * Shimmer placeholder for the gradebook page. Mirrors the real layout
 * (breadcrumb, serif H1 with export button, stats row, tabs, summary
 * card) so the page doesn't jump when data resolves.
 */
function TeacherGradebookSkeleton() {
  return (
    <div className="container mx-auto px-4 py-8 max-w-7xl" aria-busy="true">
      <div className="mb-6 flex items-center gap-2">
        <Skeleton className="h-4 w-24" />
        <Skeleton className="h-4 w-4 rounded-full" />
        <Skeleton className="h-4 w-32" />
      </div>

      <div className="mb-6 flex items-start justify-between gap-4">
        <div className="space-y-2">
          <Skeleton className="h-9 w-64 max-w-full" />
          <Skeleton className="h-4 w-40 max-w-full" />
        </div>
        <Skeleton className="h-9 w-28" />
      </div>

      <div className="mb-6 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-24 rounded-md" />
        ))}
      </div>

      <Skeleton className="mb-6 h-10 w-72 max-w-full" />

      <Skeleton className="h-96 rounded-md" />
    </div>
  )
}
