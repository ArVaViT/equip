import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { Link, Navigate, useNavigate, useParams } from "react-router-dom"
import { useTranslation } from "react-i18next"
import {
  BookOpen,
  Calendar,
  Plus,
  Search,
  Trash2,
  Users,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { DateTimePicker } from "@/components/ui/datetime-picker"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { useConfirm } from "@/components/ui/alert-dialog"
import { useAuth } from "@/context/useAuth"
import PageSpinner from "@/components/ui/PageSpinner"
import { EmptyState, ErrorState, PageHeader } from "@/components/patterns"
import { cohortsService, type CohortStudent } from "@/services/cohorts"
import { coursesService } from "@/services/courses"
import { toast } from "@/lib/toast"
import { formatDate, isoToLocalInput, localInputToIso } from "@/i18n/format"
import type { Cohort, Course } from "@/types"
import { AttachCourseDialog } from "./AttachCourseDialog"
import { AddStudentDialog } from "./AddStudentDialog"
import { CohortStatusPicker } from "./CohortStatusPicker"
import { cn } from "@/lib/utils"

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
  // Track which specific field is in-flight so saving "name" doesn't
  // also disable the date pickers and capacity input. Previously a
  // single boolean froze the whole Details card on each save which
  // looked broken on slow networks. ``null`` = nothing saving.
  const [savingField, setSavingField] = useState<string | null>(null)

  // Gate every backend call behind the admin check so a teacher or
  // logged-out visitor landing on /admin/cohorts/:id doesn't leak a
  // request out before the route-level <Navigate> redirects them.
  // Resolves the "fetch fires before redirect" timing window the
  // role-check return at the bottom of the file used to expose.
  const isAdmin = user?.role === "admin"

  const load = useCallback(async () => {
    if (!cohortId || !isAdmin) return
    setLoading(true)
    try {
      const [c, s] = await Promise.all([
        cohortsService.getCohort(cohortId),
        cohortsService.listCohortStudents(cohortId),
      ])
      setCohort(c)
      setStudents(s)
      if (c.course_ids.length) {
        // Fetch only the cohort's attached courses instead of the
        // whole catalog. ``getCourse`` is cached for 3 minutes per
        // id, so revisiting the same cohort or visiting overlapping
        // cohorts is largely free; a single cold cohort with N
        // courses costs N parallel requests instead of 1 request
        // returning the entire tenant catalog.
        const settled = await Promise.allSettled(
          c.course_ids.map((id) => coursesService.getCourse(id)),
        )
        const attached: Course[] = []
        let failed = 0
        for (const r of settled) {
          if (r.status === "fulfilled") attached.push(r.value)
          else failed += 1
        }
        setCourses(attached)
        // Surface partial failures instead of silently disappearing
        // courses from the cohort's list -- otherwise a single 500
        // on getCourse makes the admin think the course was detached
        // and reach for the wrong fix.
        if (failed > 0) {
          toast({
            title: t("admin.cohorts.toast.someCoursesFailed", { count: failed }),
            variant: "destructive",
          })
        }
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
    // ``t`` deliberately excluded -- it was here for the toast string
    // resolution, but its identity changes on every i18n language flip
    // and would trigger a full refetch (cohort + students + N courses)
    // each time the admin toggles the UI language. The toast resolves
    // ``t`` lazily at the call site anyway.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cohortId, isAdmin])

  useEffect(() => {
    void load()
  }, [load])

  const patch = async (
    fieldName: string,
    body: Parameters<typeof cohortsService.updateCohort>[1],
  ) => {
    if (!cohortId) return
    setSavingField(fieldName)
    try {
      const updated = await cohortsService.updateCohort(cohortId, body)
      setCohort(updated)
      toast({ title: t("admin.cohorts.toast.saved"), variant: "success" })
    } catch {
      toast({ title: t("admin.cohorts.toast.saveFailed"), variant: "destructive" })
    } finally {
      setSavingField(null)
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
    await patch("status", { status: next })
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
    <div className="animate-fade-in container mx-auto px-4 py-8 max-w-6xl">
      <PageHeader
        backTo="/admin?tab=cohorts"
        backLabel={t("admin.cohorts.backToList")}
        title={
          <div className="space-y-2">
            <p className="text-[11px] font-medium uppercase tracking-[0.18em] text-muted-foreground">
              {t("admin.cohorts.eyebrow")}
            </p>
            <div className="flex flex-wrap items-center gap-3">
              <h1 className="font-serif text-3xl font-bold tracking-tight text-wrap-safe">
                {cohort.name}
              </h1>
              <CohortStatusPicker
                status={cohort.status}
                disabled={savingField === "status"}
                onChange={(next) => void handleStatusChange(next)}
                ariaLabel={t("admin.cohorts.fieldStatus")}
              />
            </div>
            <p className="text-sm text-muted-foreground">
              {formatDate(cohort.start_date)} &mdash; {formatDate(cohort.end_date)}
            </p>
            {cohort.max_students != null && (
              <CapacityMeter current={cohort.student_count} cap={cohort.max_students} />
            )}
          </div>
        }
        actions={
          <Button
            variant="outline"
            size="sm"
            onClick={handleDelete}
            className="text-destructive hover:text-destructive"
          >
            <Trash2 className="mr-1.5 h-4 w-4" strokeWidth={1.75} aria-hidden />
            {t("admin.cohorts.deleteButton")}
          </Button>
        }
      />

      <Card className="mb-6">
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 font-serif text-lg font-semibold tracking-tight">
            <Calendar className="h-4 w-4" strokeWidth={1.75} aria-hidden />
            {t("admin.cohorts.detailsHeading")}
          </CardTitle>
        </CardHeader>
        <CardContent className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <Field
            label={t("admin.cohorts.fieldName")}
            value={cohort.name}
            onSave={(v) => patch("name", { name: v })}
            disabled={savingField === "name"}
          />
          <Field
            label={t("admin.cohorts.fieldMaxStudents")}
            value={cohort.max_students == null ? "" : String(cohort.max_students)}
            placeholder={t("admin.cohorts.unlimited")}
            disabled={savingField === "max_students"}
            onSave={(v) => {
              // Empty string -> ``null`` (unlimited). Number() trims
              // whitespace; the input is ``type="number"`` so non-digit
              // garbage is already filtered by the browser.
              const n = v ? Number(v) : null
              void patch("max_students", { max_students: n })
            }}
            inputType="number"
          />
          <DateField
            label={t("admin.cohorts.fieldStart")}
            value={cohort.start_date}
            onSave={(iso) => {
              if (iso) void patch("start_date", { start_date: iso })
            }}
            disabled={savingField === "start_date"}
          />
          <DateField
            label={t("admin.cohorts.fieldEnd")}
            value={cohort.end_date}
            onSave={(iso) => {
              if (iso) void patch("end_date", { end_date: iso })
            }}
            disabled={savingField === "end_date"}
          />
          <DateField
            label={t("admin.cohorts.fieldEnrollStart")}
            value={cohort.enrollment_start}
            onSave={(iso) => patch("enrollment_start", { enrollment_start: iso })}
            disabled={savingField === "enrollment_start"}
            nullable
          />
          <DateField
            label={t("admin.cohorts.fieldEnrollEnd")}
            value={cohort.enrollment_end}
            onSave={(iso) => patch("enrollment_end", { enrollment_end: iso })}
            disabled={savingField === "enrollment_end"}
            nullable
          />
        </CardContent>
      </Card>

      <Card className="mb-6">
        <CardHeader className="flex-row items-center justify-between space-y-0 pb-3">
          <CardTitle className="font-serif text-lg font-semibold tracking-tight">
            {t("admin.cohorts.coursesHeading", { count: courses.length })}
          </CardTitle>
          <Button size="sm" className="h-9" onClick={() => setAttachOpen(true)}>
            <Plus className="mr-1.5 h-4 w-4" strokeWidth={1.75} aria-hidden />
            {t("admin.cohorts.attachCourseButton")}
          </Button>
        </CardHeader>
        <CardContent className="pt-0">
          {courses.length === 0 ? (
            <EmptyState
              icon={<BookOpen strokeWidth={1.75} aria-hidden />}
              title={t("admin.cohorts.noCoursesAttachedTitle")}
              description={t("admin.cohorts.noCoursesAttached")}
              action={
                <Button size="sm" variant="outline" onClick={() => setAttachOpen(true)}>
                  <Plus className="mr-1.5 h-4 w-4" strokeWidth={1.75} aria-hidden />
                  {t("admin.cohorts.attachCourseButton")}
                </Button>
              }
            />
          ) : (
            // Inline list of course chips — dense, visually consistent
            // with the rest of the admin row vocabulary (Vercel-style
            // "row of pills with a trailing remove"). Each chip links
            // to the course detail; the trash button stops propagation
            // so the remove confirmation doesn't double-fire on click.
            <ul className="flex flex-col gap-2">
              {courses.map((c) => (
                <li
                  key={c.id}
                  className="flex items-center justify-between gap-3 rounded-md border border-border bg-muted/10 px-3 py-2 transition-colors hover:border-primary/30 hover:bg-muted/40"
                >
                  <div className="flex min-w-0 items-center gap-2">
                    <Link
                      to={`/teacher/courses/${c.id}`}
                      className="truncate text-sm font-medium text-foreground hover:text-primary"
                    >
                      {c.title}
                    </Link>
                    {c.access_mode === "institute" && (
                      <Badge variant="muted" className="shrink-0 font-normal">
                        {t("courseCard.byInvitation")}
                      </Badge>
                    )}
                  </div>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-8 w-8 shrink-0 p-0 text-muted-foreground hover:text-destructive"
                    onClick={() => detachCourse(c.id)}
                    aria-label={t("admin.cohorts.detachAriaPrefix", { name: c.title })}
                  >
                    <Trash2 className="h-4 w-4" strokeWidth={1.75} aria-hidden />
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      <StudentsCard students={students} onAdd={() => setAddOpen(true)} onRemove={removeStudent} />

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
  /** Fires once on blur (or Enter) IF the value actually changed from
   *  the last value we sync'd in from the parent. The field owns the
   *  diff check so callers don't each rewrite it (and so the check
   *  uses our ``lastSyncedRef`` baseline instead of a stale closure
   *  over ``cohort.someField``). */
  onSave: (next: string) => void
}

function Field({ label, value, placeholder, inputType = "text", disabled, onSave }: FieldProps) {
  const [local, setLocal] = useState(value)
  const inputRef = useRef<HTMLInputElement>(null)
  // Baseline of "what the server believes this value is" -- used both
  // to skip no-op PATCHes and to know when an externally-changed prop
  // should overwrite the local draft.
  const lastSyncedRef = useRef(value)

  useEffect(() => {
    // Pull updates from the prop, but ONLY when the field isn't being
    // edited AND the prop actually changed. Without the focus guard a
    // sibling save (which causes the parent ``cohort`` to re-render
    // even though THIS field's string is unchanged) would still run
    // this effect on every render in some setups and could clobber a
    // half-typed draft.
    if (value === lastSyncedRef.current) return
    const isEditing =
      typeof document !== "undefined" && document.activeElement === inputRef.current
    if (isEditing) return
    setLocal(value)
    lastSyncedRef.current = value
  }, [value])

  const commit = () => {
    if (local === lastSyncedRef.current) return
    lastSyncedRef.current = local
    onSave(local)
  }

  return (
    <div className="space-y-1.5">
      <Label className="text-xs">{label}</Label>
      <Input
        ref={inputRef}
        type={inputType}
        value={local}
        placeholder={placeholder}
        disabled={disabled}
        onChange={(e) => setLocal(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === "Enter") (e.target as HTMLInputElement).blur()
          else if (e.key === "Escape") {
            setLocal(lastSyncedRef.current)
            ;(e.target as HTMLInputElement).blur()
          }
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
  // Mirror the same baseline guard as ``Field``: don't PATCH when the
  // picker fires onChange with a value equivalent to the current ISO.
  // The picker re-fires on every internal state tick (clicking the
  // calendar can produce multiple onChange events with the same iso),
  // and without this guard each tick costs a network round-trip plus a
  // toast.
  const lastSyncedRef = useRef<string | null>(value)
  useEffect(() => {
    lastSyncedRef.current = value
  }, [value])

  return (
    <div className="space-y-1.5">
      <Label className="text-xs">{label}</Label>
      <DateTimePicker
        value={local}
        disabled={disabled}
        onChange={(next) => {
          if (!next) {
            if (nullable && lastSyncedRef.current !== null) {
              lastSyncedRef.current = null
              void onSave(null)
            }
            return
          }
          const iso = localInputToIso(next)
          if (!iso) return
          if (iso === lastSyncedRef.current) return
          lastSyncedRef.current = iso
          void onSave(iso)
        }}
        className="w-full"
      />
    </div>
  )
}

/**
 * Horizontal capacity bar — quick read of "how full is this cohort".
 * Tone shifts from primary → warning → destructive as utilisation
 * climbs past 75% / 95% so an admin scanning multiple cohorts can
 * spot the near-full ones without reading the X/Y numbers each time.
 */
function CapacityMeter({ current, cap }: { current: number; cap: number }) {
  const { t } = useTranslation()
  const safeCap = Math.max(cap, 1)
  const pct = Math.min(100, Math.round((current / safeCap) * 100))
  const tone = pct >= 95 ? "bg-destructive" : pct >= 75 ? "bg-warning" : "bg-primary"
  return (
    <div className="mt-3 max-w-xs">
      <div className="flex items-baseline justify-between gap-3 text-xs">
        <span className="font-medium tabular-nums text-foreground">
          {current} / {cap}
        </span>
        <span className="text-muted-foreground">
          {t("admin.cohorts.capacityLabel", { pct })}
        </span>
      </div>
      <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-muted">
        <div
          className={cn("h-full rounded-full transition-all duration-500", tone)}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  )
}

/**
 * Students panel with search + sticky-header internal-scroll table —
 * same shape as the audit log so the admin's table vocabulary stays
 * consistent across surfaces. Search is client-side over the already-
 * loaded ``students`` list; the cohort list size stays in the low
 * hundreds so a per-keystroke server round-trip isn't worth it.
 */
function StudentsCard({
  students,
  onAdd,
  onRemove,
}: {
  students: CohortStudent[]
  onAdd: () => void
  onRemove: (s: CohortStudent) => void
}) {
  const { t } = useTranslation()
  const [search, setSearch] = useState("")
  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    if (!q) return students
    return students.filter(
      (s) =>
        (s.full_name ?? "").toLowerCase().includes(q) ||
        s.email.toLowerCase().includes(q),
    )
  }, [students, search])

  return (
    <Card>
      <CardHeader className="gap-3 space-y-0">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <CardTitle className="flex items-center gap-2 font-serif text-lg font-semibold tracking-tight">
            <Users className="h-4 w-4" strokeWidth={1.75} aria-hidden />
            {t("admin.cohorts.studentsHeading", { count: students.length })}
          </CardTitle>
          <Button size="sm" onClick={onAdd}>
            <Plus className="mr-1.5 h-4 w-4" strokeWidth={1.75} aria-hidden />
            {t("admin.cohorts.addStudentButton")}
          </Button>
        </div>
        {students.length > 0 && (
          <div className="relative">
            <Search
              className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground"
              strokeWidth={1.75}
              aria-hidden
            />
            <Input
              fieldSize="sm"
              placeholder={t("admin.cohorts.studentSearchPlaceholder")}
              value={search}
              onChange={(e) => setSearch(e.target.value.slice(0, 100))}
              maxLength={100}
              className="pl-9"
            />
          </div>
        )}
      </CardHeader>
      <CardContent className="p-0">
        {students.length === 0 ? (
          <EmptyState
            icon={<Users strokeWidth={1.75} aria-hidden />}
            title={t("admin.cohorts.noStudentsTitle")}
            description={t("admin.cohorts.noStudents")}
            action={
              <Button size="sm" variant="outline" onClick={onAdd}>
                <Plus className="mr-1.5 h-4 w-4" strokeWidth={1.75} aria-hidden />
                {t("admin.cohorts.addStudentButton")}
              </Button>
            }
          />
        ) : filtered.length === 0 ? (
          <EmptyState
            icon={<Search strokeWidth={1.75} aria-hidden />}
            title={t("admin.cohorts.studentSearchNoMatch")}
            description={t("admin.cohorts.studentSearchNoMatchHint")}
          />
        ) : (
          <div className="max-h-[55vh] overflow-y-auto">
            <table className="w-full text-sm">
              <thead className="sticky top-0 z-10 bg-card">
                <tr className="border-b text-left">
                  <th className="px-5 py-3 font-medium text-muted-foreground">
                    {t("admin.cohorts.thStudentName")}
                  </th>
                  <th className="px-5 py-3 font-medium text-muted-foreground">
                    {t("admin.cohorts.thStudentEmail")}
                  </th>
                  <th className="px-5 py-3 font-medium text-muted-foreground">
                    {t("admin.cohorts.thEnrolledCourses")}
                  </th>
                  <th className="w-10 px-5 py-3" aria-label={t("admin.cohorts.thActions")} />
                </tr>
              </thead>
              <tbody className="divide-y">
                {filtered.map((s) => (
                  <tr key={s.user_id} className="transition-colors hover:bg-muted/40">
                    <td className="px-5 py-3 font-medium">{s.full_name ?? "—"}</td>
                    <td className="px-5 py-3 text-xs text-muted-foreground">{s.email}</td>
                    <td className="px-5 py-3 text-muted-foreground tabular-nums">
                      {Object.keys(s.per_course).length}
                    </td>
                    <td className="px-3 py-3">
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-8 w-8 p-0 text-muted-foreground hover:text-destructive"
                        onClick={() => onRemove(s)}
                        aria-label={t("admin.cohorts.removeStudentAriaPrefix", {
                          name: s.full_name ?? s.email,
                        })}
                      >
                        <Trash2 className="h-4 w-4" strokeWidth={1.75} aria-hidden />
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
  )
}
