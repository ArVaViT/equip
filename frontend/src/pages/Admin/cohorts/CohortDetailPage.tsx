import { useCallback, useEffect, useState } from "react"
import { Link, Navigate, useNavigate, useParams } from "react-router-dom"
import { useTranslation } from "react-i18next"
import {
  ArrowLeft,
  Calendar,
  Plus,
  Trash2,
  Users,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { useConfirm } from "@/components/ui/alert-dialog"
import { useAuth } from "@/context/useAuth"
import PageSpinner from "@/components/ui/PageSpinner"
import { ErrorState } from "@/components/patterns"
import { cohortsService, type CohortStudent } from "@/services/cohorts"
import { coursesService } from "@/services/courses"
import { toast } from "@/lib/toast"
import { formatDate, isoToLocalInput, localInputToIso } from "@/i18n/format"
import type { Cohort, Course } from "@/types"
import { AttachCourseDialog } from "./AttachCourseDialog"
import { AddStudentDialog } from "./AddStudentDialog"
import { CohortStatusPicker } from "./CohortStatusPicker"

export default function CohortDetailPage() {
  const { cohortId } = useParams<{ cohortId: string }>()
  const { user } = useAuth()
  const { t } = useTranslation()
  const navigate = useNavigate()
  const confirm = useConfirm()

  const [cohort, setCohort] = useState<Cohort | null>(null)
  const [courses, setCourses] = useState<Course[]>([])
  const [students, setStudents] = useState<CohortStudent[]>([])
  const [loading, setLoading] = useState(true)
  const [notFound, setNotFound] = useState(false)
  const [attachOpen, setAttachOpen] = useState(false)
  const [addOpen, setAddOpen] = useState(false)
  const [savingField, setSavingField] = useState(false)

  const load = useCallback(async () => {
    if (!cohortId) return
    setLoading(true)
    try {
      const [c, s] = await Promise.all([
        cohortsService.getCohort(cohortId),
        cohortsService.listCohortStudents(cohortId),
      ])
      setCohort(c)
      setStudents(s)
      if (c.course_ids.length) {
        const all = await coursesService.getCourses()
        const attached = all.filter((co) => c.course_ids.includes(co.id))
        setCourses(attached)
      } else {
        setCourses([])
      }
    } catch (e: unknown) {
      const status = (e as { response?: { status?: number } })?.response?.status
      if (status === 404) setNotFound(true)
      else toast({ title: t("admin.cohorts.toast.loadFailed"), variant: "destructive" })
    } finally {
      setLoading(false)
    }
  }, [cohortId, t])

  useEffect(() => {
    void load()
  }, [load])

  const patch = async (body: Parameters<typeof cohortsService.updateCohort>[1]) => {
    if (!cohortId) return
    setSavingField(true)
    try {
      const updated = await cohortsService.updateCohort(cohortId, body)
      setCohort(updated)
      toast({ title: t("admin.cohorts.toast.saved"), variant: "success" })
    } catch {
      toast({ title: t("admin.cohorts.toast.saveFailed"), variant: "destructive" })
    } finally {
      setSavingField(false)
    }
  }

  /**
   * Status is edited through the single ``CohortStatusPicker`` in the
   * page header — the badge IS the picker (same pattern as
   * ``RoleSelector``). Previously the status was rendered twice (the
   * coloured header badge and a separate ``NativeSelect`` in the
   * Details card); collapsed to one affordance.
   *
   * Transitioning to ``completed`` still confirms first because it's
   * a one-way operation in practice (the cohort stops being editable).
   */
  const handleStatusChange = async (next: Cohort["status"]) => {
    if (!cohortId || next === cohort?.status) return
    if (next === "completed") {
      const ok = await confirm({
        title: t("admin.cohorts.completeConfirmTitle"),
        description: t("admin.cohorts.completeConfirmDescription"),
        confirmLabel: t("admin.cohorts.completeConfirmAction"),
      })
      if (!ok) return
    }
    await patch({ status: next })
  }

  const handleDelete = async () => {
    if (!cohortId) return
    const ok = await confirm({
      title: t("admin.cohorts.deleteConfirmTitle"),
      description: t("admin.cohorts.deleteConfirmDescription"),
      confirmLabel: t("admin.cohorts.deleteConfirmAction"),
      tone: "destructive",
    })
    if (!ok) return
    try {
      await cohortsService.deleteCohort(cohortId)
      toast({ title: t("admin.cohorts.toast.deleted"), variant: "success" })
      navigate("/admin?tab=cohorts")
    } catch {
      toast({ title: t("admin.cohorts.toast.deleteFailed"), variant: "destructive" })
    }
  }

  const detachCourse = async (courseId: string) => {
    if (!cohortId) return
    const c = courses.find((co) => co.id === courseId)
    const ok = await confirm({
      title: t("admin.cohorts.detachConfirmTitle", { name: c?.title ?? "" }),
      description: t("admin.cohorts.detachConfirmDescription"),
      confirmLabel: t("admin.cohorts.detachConfirmAction"),
      tone: "destructive",
    })
    if (!ok) return
    try {
      await cohortsService.detachCourseFromCohort(cohortId, courseId)
      toast({ title: t("admin.cohorts.toast.detached"), variant: "success" })
      await load()
    } catch {
      toast({ title: t("admin.cohorts.toast.detachFailed"), variant: "destructive" })
    }
  }

  const removeStudent = async (s: CohortStudent) => {
    if (!cohortId) return
    const ok = await confirm({
      title: t("admin.cohorts.removeStudentConfirmTitle", {
        name: s.full_name ?? s.email,
      }),
      description: t("admin.cohorts.removeStudentConfirmDescription"),
      confirmLabel: t("admin.cohorts.removeStudentConfirmAction"),
      tone: "destructive",
    })
    if (!ok) return
    try {
      await cohortsService.removeCohortStudent(cohortId, s.user_id)
      toast({ title: t("admin.cohorts.toast.studentRemoved"), variant: "success" })
      await load()
    } catch {
      toast({ title: t("admin.cohorts.toast.removeFailed"), variant: "destructive" })
    }
  }

  if (user?.role !== "admin") return <Navigate to="/" replace />
  if (loading) return <PageSpinner />
  if (notFound || !cohort) {
    return (
      <div className="container mx-auto px-4 py-8 max-w-6xl">
        <ErrorState
          title={t("admin.cohorts.notFoundTitle")}
          description={t("admin.cohorts.notFoundDescription")}
          action={
            <Link to="/admin?tab=cohorts">
              <Button size="sm" variant="outline">
                {t("admin.cohorts.backToList")}
              </Button>
            </Link>
          }
        />
      </div>
    )
  }

  return (
    <div className="animate-fade-in container mx-auto px-4 py-8 max-w-5xl">
      <Link to="/admin?tab=cohorts">
        <Button variant="ghost" size="sm" className="mb-4 h-8 text-xs">
          <ArrowLeft className="mr-1.5 h-4 w-4" strokeWidth={1.75} aria-hidden />
          {t("admin.cohorts.backToList")}
        </Button>
      </Link>

      <div className="flex items-start justify-between gap-4 flex-wrap mb-8">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-3 mb-2">
            <h1 className="text-3xl font-serif font-bold tracking-tight text-wrap-safe">
              {cohort.name}
            </h1>
            <CohortStatusPicker
              status={cohort.status}
              disabled={savingField}
              onChange={(next) => void handleStatusChange(next)}
              ariaLabel={t("admin.cohorts.fieldStatus")}
            />
          </div>
          <p className="text-sm text-muted-foreground">
            {formatDate(cohort.start_date)} &mdash; {formatDate(cohort.end_date)}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={handleDelete} className="text-destructive hover:text-destructive">
            <Trash2 className="h-4 w-4 mr-1.5" strokeWidth={1.75} aria-hidden />
            {t("admin.cohorts.deleteButton")}
          </Button>
        </div>
      </div>

      <Card className="mb-8">
        <CardHeader>
          <CardTitle className="text-lg flex items-center gap-2">
            <Calendar className="h-4 w-4" strokeWidth={1.75} aria-hidden />
            {t("admin.cohorts.detailsHeading")}
          </CardTitle>
        </CardHeader>
        <CardContent className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <Field
            label={t("admin.cohorts.fieldName")}
            value={cohort.name}
            onBlurSave={(v) => v !== cohort.name && patch({ name: v })}
            disabled={savingField}
          />
          <Field
            label={t("admin.cohorts.fieldMaxStudents")}
            value={cohort.max_students == null ? "" : String(cohort.max_students)}
            placeholder={t("admin.cohorts.unlimited")}
            disabled={savingField}
            onBlurSave={(v) => {
              const n = v ? Number(v) : null
              if (n === cohort.max_students) return
              void patch({ max_students: n })
            }}
            inputType="number"
          />
          <DateField
            label={t("admin.cohorts.fieldStart")}
            value={cohort.start_date}
            onSave={(iso) => {
              if (iso) void patch({ start_date: iso })
            }}
            disabled={savingField}
          />
          <DateField
            label={t("admin.cohorts.fieldEnd")}
            value={cohort.end_date}
            onSave={(iso) => {
              if (iso) void patch({ end_date: iso })
            }}
            disabled={savingField}
          />
          <DateField
            label={t("admin.cohorts.fieldEnrollStart")}
            value={cohort.enrollment_start}
            onSave={(iso) => patch({ enrollment_start: iso })}
            disabled={savingField}
            nullable
          />
          <DateField
            label={t("admin.cohorts.fieldEnrollEnd")}
            value={cohort.enrollment_end}
            onSave={(iso) => patch({ enrollment_end: iso })}
            disabled={savingField}
            nullable
          />
        </CardContent>
      </Card>

      <Card className="mb-8">
        <CardHeader className="flex-row items-center justify-between space-y-0">
          <CardTitle className="text-lg">
            {t("admin.cohorts.coursesHeading", { count: courses.length })}
          </CardTitle>
          <Button size="sm" onClick={() => setAttachOpen(true)}>
            <Plus className="h-4 w-4 mr-1.5" strokeWidth={1.75} aria-hidden />
            {t("admin.cohorts.attachCourseButton")}
          </Button>
        </CardHeader>
        <CardContent>
          {courses.length === 0 ? (
            <p className="text-sm text-muted-foreground py-4">
              {t("admin.cohorts.noCoursesAttached")}
            </p>
          ) : (
            <ul className="divide-y">
              {courses.map((c) => (
                <li key={c.id} className="flex items-center justify-between py-3">
                  <div>
                    <Link to={`/teacher/courses/${c.id}`} className="font-medium hover:text-primary">
                      {c.title}
                    </Link>
                    {c.access_mode === "institute" && (
                      <Badge variant="muted" className="ml-2">
                        {t("courseCard.byInvitation")}
                      </Badge>
                    )}
                  </div>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="text-muted-foreground hover:text-destructive"
                    onClick={() => detachCourse(c.id)}
                    aria-label={t("admin.cohorts.detachAriaPrefix", { name: c.title })}
                  >
                    <Trash2 className="h-4 w-4" strokeWidth={1.75} />
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex-row items-center justify-between space-y-0">
          <CardTitle className="text-lg flex items-center gap-2">
            <Users className="h-4 w-4" strokeWidth={1.75} aria-hidden />
            {t("admin.cohorts.studentsHeading", { count: students.length })}
          </CardTitle>
          <Button size="sm" onClick={() => setAddOpen(true)}>
            <Plus className="h-4 w-4 mr-1.5" strokeWidth={1.75} aria-hidden />
            {t("admin.cohorts.addStudentButton")}
          </Button>
        </CardHeader>
        <CardContent>
          {students.length === 0 ? (
            <p className="text-sm text-muted-foreground py-4">
              {t("admin.cohorts.noStudents")}
            </p>
          ) : (
            <div className="overflow-x-auto -mx-6">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left">
                    <th className="px-6 py-3 font-medium text-muted-foreground">
                      {t("admin.cohorts.thStudentName")}
                    </th>
                    <th className="px-6 py-3 font-medium text-muted-foreground">
                      {t("admin.cohorts.thStudentEmail")}
                    </th>
                    <th className="px-6 py-3 font-medium text-muted-foreground">
                      {t("admin.cohorts.thEnrolledCourses")}
                    </th>
                    <th className="px-6 py-3 w-10" aria-label={t("admin.cohorts.thActions")} />
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {students.map((s) => (
                    <tr key={s.user_id} className="hover:bg-muted/50 transition-colors">
                      <td className="px-6 py-3 font-medium">{s.full_name ?? "—"}</td>
                      <td className="px-6 py-3 text-muted-foreground">{s.email}</td>
                      <td className="px-6 py-3 text-muted-foreground">
                        {Object.keys(s.per_course).length}
                      </td>
                      <td className="px-3 py-3">
                        <Button
                          variant="ghost"
                          size="sm"
                          className="h-8 w-8 p-0 text-muted-foreground hover:text-destructive"
                          onClick={() => removeStudent(s)}
                          aria-label={t("admin.cohorts.removeStudentAriaPrefix", {
                            name: s.full_name ?? s.email,
                          })}
                        >
                          <Trash2 className="h-4 w-4" strokeWidth={1.75} />
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      <AttachCourseDialog
        open={attachOpen}
        onClose={() => setAttachOpen(false)}
        cohortId={cohort.id}
        attachedCourseIds={cohort.course_ids}
        onAttached={() => {
          setAttachOpen(false)
          void load()
        }}
      />
      <AddStudentDialog
        open={addOpen}
        onClose={() => setAddOpen(false)}
        cohortId={cohort.id}
        onAdded={() => {
          setAddOpen(false)
          void load()
        }}
      />
    </div>
  )
}

interface FieldProps {
  label: string
  value: string
  placeholder?: string
  inputType?: string
  disabled?: boolean
  onBlurSave: (next: string) => void
}

function Field({ label, value, placeholder, inputType = "text", disabled, onBlurSave }: FieldProps) {
  const [local, setLocal] = useState(value)
  useEffect(() => setLocal(value), [value])
  return (
    <div className="space-y-1.5">
      <Label className="text-xs">{label}</Label>
      <Input
        type={inputType}
        value={local}
        placeholder={placeholder}
        disabled={disabled}
        onChange={(e) => setLocal(e.target.value)}
        onBlur={() => onBlurSave(local)}
        onKeyDown={(e) => {
          if (e.key === "Enter") (e.target as HTMLInputElement).blur()
        }}
      />
    </div>
  )
}

interface DateFieldProps {
  label: string
  value: string | null
  disabled?: boolean
  nullable?: boolean
  onSave: (iso: string | null) => Promise<void> | void
}

function DateField({ label, value, disabled, nullable, onSave }: DateFieldProps) {
  const local = isoToLocalInput(value)
  return (
    <div className="space-y-1.5">
      <Label className="text-xs">{label}</Label>
      <Input
        type="datetime-local"
        value={local}
        disabled={disabled}
        onChange={(e) => {
          const v = e.target.value
          if (!v) {
            if (nullable) void onSave(null)
            return
          }
          const iso = localInputToIso(v)
          if (iso) void onSave(iso)
        }}
      />
    </div>
  )
}
