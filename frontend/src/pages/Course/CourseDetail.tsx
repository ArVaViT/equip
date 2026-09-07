import { useEffect, useMemo, useState } from "react"
import { useTranslation } from "react-i18next"
import { useParams, Link } from "react-router-dom"
import { isAxiosError } from "axios"
import { BookOpen } from "lucide-react"
import { Button } from "@/components/ui/button"
import { ErrorState } from "@/components/patterns"
import { coursesService } from "@/services/courses"
import { storageService } from "@/services/storage"
import { recordCourseView } from "@/lib/recentlyViewed"
import { readCourseStructure } from "@/lib/courseStructure"
import { useAuth } from "@/context/useAuth"
import { toast } from "@/lib/toast"
import { ROLES } from "@/types"
import type {
  CalendarEvent,
  Certificate,
  Cohort,
  Course,
  Enrollment,
} from "@/types"
import {
  CourseDetailSkeleton,
  EnrolledView,
  NotEnrolledView,
  type CourseMaterial,
} from "./detail"

export default function CourseDetail() {
  const { t, i18n } = useTranslation()
  const { id } = useParams<{ id: string }>()
  const { user } = useAuth()
  const [course, setCourse] = useState<Course | null>(null)
  const [enrollment, setEnrollment] = useState<Enrollment | null>(null)
  const [certificate, setCertificate] = useState<Certificate | null>(null)
  /**
   * `null` when the progress request failed. Not an empty set.
   *
   * This is the third place the same fallback lived, and the worst of the
   * three: `CourseOutline` locks a whole module behind the previous one, so a
   * failed request walled a student out of everything after the module they
   * had actually completed. See `moduleProgress.ts`.
   */
  const [completedChapterIds, setCompletedChapterIds] = useState<Set<string> | null>(null)
  const [materials, setMaterials] = useState<CourseMaterial[]>([])
  const [cohorts, setCohorts] = useState<Cohort[]>([])
  const [calendarEvents, setCalendarEvents] = useState<CalendarEvent[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [enrolling, setEnrolling] = useState(false)

  useEffect(() => {
    let cancelled = false
    const load = async () => {
      if (!id) return
      setLoading(true)
      setError(null)
      setCourse(null)
      setEnrollment(null)
      setCertificate(null)
      setCompletedChapterIds(new Set())
      setMaterials([])
      setCalendarEvents([])
      setCohorts([])
      try {
        // Speculatively kick off the enrollment-dependent fetches
        // alongside the first batch when ``user`` is present, so the
        // request round-trip only happens once. Previously this code
        // awaited the enrollment-check result, THEN issued the second
        // batch — a sequential waterfall that doubled the latency for
        // every enrolled student loading a course page. The
        // speculative calls cost 4 cheap GETs per non-enrolled
        // logged-in user (still a single round-trip), but the
        // enrolled-student path saves an entire RTT. Anonymous users
        // pay nothing — the user-gated promises short-circuit to
        // their empty defaults.
        // Not caught: «we could not find out» must not become «not
        // enrolled». It did, and an enrolled student whose check timed out
        // saw the enrol page with their modules, progress and certificate
        // gone — and no error anywhere. A failed check fails the page.
        const enrolled = user
          ? coursesService.getEnrollmentStatus(id)
          : Promise.resolve({ enrolled: false, enrollment: null as Enrollment | null })
        const certP = user
          ? coursesService.getCourseCertificate(id).catch(() => null)
          : Promise.resolve(null)
        const progressP = user
          ? coursesService.getMyChapterProgress(id).catch(() => null)
          : Promise.resolve([] as string[])
        const matsP = user
          ? storageService.listCourseMaterials(id).catch(() => [] as CourseMaterial[])
          : Promise.resolve([] as CourseMaterial[])
        const evtsP = user
          ? coursesService.getCalendarEvents(id).catch(() => [] as CalendarEvent[])
          : Promise.resolve([] as CalendarEvent[])

        const [courseData, enrollmentStatus, cohortsData, cert, progress, mats, evts] = await Promise.all([
          coursesService.getCourse(id),
          enrolled,
          coursesService.getCourseCohorts(id).catch(() => [] as Cohort[]),
          certP,
          progressP,
          matsP,
          evtsP,
        ])
        if (cancelled) return
        setCourse(courseData)
        setCohorts(cohortsData)
        const match = enrollmentStatus.enrolled ? enrollmentStatus.enrollment : null
        if (match) {
          setEnrollment(match)
          setCertificate(cert)
          setCompletedChapterIds(progress === null ? null : new Set(progress))
          setMaterials(mats)
          setCalendarEvents(evts)
        }
      } catch (err) {
        if (!cancelled) {
          setError(
            isAxiosError(err) && err.response?.status === 404
              ? t("toast.courseNotFound")
              : t("errors.loadCourseFailed"),
          )
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    void load()
    return () => {
      cancelled = true
    }
    // Reload only when course id, user identity, or active locale
    // change. Plain ``user`` would refetch on every Supabase
    // TOKEN_REFRESHED tick (the auth context rewrites the object);
    // ``i18n.language`` covers the locale-flip case so the course
    // title / module names / chapter list re-pull localised values
    // without a hard reload. ``t`` is intentionally NOT in the dep
    // list — its reference change is implementation-defined.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, user?.id, i18n.language])

  // Track this course in the dashboard's "recently viewed" row. Only for
  // signed-in users (anonymous visitors don't have a dashboard) and only
  // once the course actually resolved, so a 404 / failed load doesn't
  // pin a dead id. Filtered against real enrollments at render time.
  useEffect(() => {
    if (user && course?.id) {
      recordCourseView(course.id)
    }
  }, [user, course?.id])

  const doEnroll = async (cohortId?: string) => {
    if (!id || !user) return
    setEnrolling(true)
    try {
      const enrolled = await coursesService.enrollInCourse(id, cohortId)
      setEnrollment(enrolled)
      const [cert, progress, mats, evts] = await Promise.all([
        coursesService.getCourseCertificate(id),
        coursesService.getMyChapterProgress(id).catch(() => null),
        storageService.listCourseMaterials(id).catch(() => [] as CourseMaterial[]),
        coursesService.getCalendarEvents(id).catch(() => [] as CalendarEvent[]),
      ])
      setCertificate(cert)
      setCompletedChapterIds(progress === null ? null : new Set(progress))
      setMaterials(mats)
      setCalendarEvents(evts)
      toast({ title: t("toast.enrolledSuccess"), variant: "success" })
    } catch {
      toast({ title: t("toast.enrolledFailed"), variant: "destructive" })
    } finally {
      setEnrolling(false)
    }
  }

  /**
   * The course read once: the outline to draw, and the flat reading order
   * everything downstream navigates by.
   *
   * It replaces a pair of derivations that could only see modules — a module
   * sort and a chapter total summed over `modules[].chapters`. A lesson in no
   * module was in neither, so the course page counted it out of existence and
   * the outline never drew it.
   *
   * The module sort it replaces ordered by `due_date` first and `order_index`
   * second, which is a second opinion about the order of a course: the server,
   * the teacher's report, the PDF export and the gradebook all read
   * `order_index`. Two orders is how «the next lesson» and «the lesson after
   * this row» stopped agreeing. There is one order now, and it is the
   * teacher's. A module's deadline still shows on its row.
   *
   * Memoised on ``course`` so `EnrolledView` gets a stable identity across
   * renders that don't change the payload (a certificate update, say). Hooks
   * must run before the early returns below — this no-ops to an empty
   * structure while ``course`` is still null during load.
   */
  const structure = useMemo(() => readCourseStructure(course), [course])

  if (loading) {
    return <CourseDetailSkeleton />
  }

  if (error || !course) {
    return (
      <div className="container mx-auto px-4">
        <ErrorState
          icon={<BookOpen strokeWidth={1.75} />}
          title={error ?? t("toast.courseNotFound")}
          action={
            <Link to="/courses">
              <Button variant="outline" size="sm">
                {t("course.backToCourses")}
              </Button>
            </Link>
          }
        />
      </div>
    )
  }

  const isOwner = user?.id === course.created_by || user?.role === ROLES.ADMIN

  if (!enrollment) {
    return (
      <NotEnrolledView
        course={course}
        cohorts={cohorts}
        isOwner={isOwner}
        isSignedIn={!!user}
        enrolling={enrolling}
        onEnroll={doEnroll}
      />
    )
  }

  return (
    <EnrolledView
      course={course}
      enrollment={enrollment}
      cohorts={cohorts}
      structure={structure}
      completedChapterIds={completedChapterIds}
      materials={materials}
      calendarEvents={calendarEvents}
      certificate={certificate}
      onCertificateUpdate={setCertificate}
    />
  )
}
