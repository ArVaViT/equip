import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { useParams, Link } from "react-router-dom"
import { BookOpen } from "lucide-react"
import { Button } from "@/components/ui/button"
import { ErrorState } from "@/components/patterns"
import { coursesService } from "@/services/courses"
import { storageService } from "@/services/storage"
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
  const [completedChapterIds, setCompletedChapterIds] = useState<Set<string>>(new Set())
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
        const enrolled = user
          ? coursesService
              .getEnrollmentStatus(id)
              .catch(() => ({ enrolled: false, enrollment: null as Enrollment | null }))
          : Promise.resolve({ enrolled: false, enrollment: null as Enrollment | null })
        const certP = user
          ? coursesService.getCourseCertificate(id).catch(() => null)
          : Promise.resolve(null)
        const progressP = user
          ? coursesService.getMyChapterProgress(id).catch(() => [] as string[])
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
          setCompletedChapterIds(new Set(progress))
          setMaterials(mats)
          setCalendarEvents(evts)
        }
      } catch {
        if (!cancelled) setError(t("errors.loadCourseFailed"))
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

  const doEnroll = async (cohortId?: string) => {
    if (!id || !user) return
    setEnrolling(true)
    try {
      const enrolled = await coursesService.enrollInCourse(id, cohortId)
      setEnrollment(enrolled)
      const [cert, progress, mats, evts] = await Promise.all([
        coursesService.getCourseCertificate(id),
        coursesService.getMyChapterProgress(id).catch(() => [] as string[]),
        storageService.listCourseMaterials(id).catch(() => [] as CourseMaterial[]),
        coursesService.getCalendarEvents(id).catch(() => [] as CalendarEvent[]),
      ])
      setCertificate(cert)
      setCompletedChapterIds(new Set(progress))
      setMaterials(mats)
      setCalendarEvents(evts)
      toast({ title: t("toast.enrolledSuccess"), variant: "success" })
    } catch {
      toast({ title: t("toast.enrolledFailed"), variant: "destructive" })
    } finally {
      setEnrolling(false)
    }
  }

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
  const sortedModules = [...(course.modules ?? [])].sort((a, b) => {
    const da = a.due_date ? new Date(a.due_date).getTime() : Infinity
    const db = b.due_date ? new Date(b.due_date).getTime() : Infinity
    if (da !== db) return da - db
    return a.order_index - b.order_index
  })
  const totalChapters = sortedModules.reduce(
    (sum, m) => sum + (m.chapters?.length ?? 0),
    0,
  )

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
      sortedModules={sortedModules}
      totalChapters={totalChapters}
      completedChapterIds={completedChapterIds}
      materials={materials}
      calendarEvents={calendarEvents}
      certificate={certificate}
      onCertificateUpdate={setCertificate}
    />
  )
}
