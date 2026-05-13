import { useState } from "react"
import { Link } from "react-router-dom"
import { useTranslation } from "react-i18next"
import { ArrowLeft, CalendarDays, Clock, Users } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { toProxyImage } from "@/lib/images"
import type { Course, Cohort } from "@/types"
import { formatDate, isEnrollableCohort } from "./types"
import { CohortSelectModal } from "./CohortSelectModal"

interface Props {
  course: Course
  cohorts: Cohort[]
  isOwner: boolean
  isSignedIn: boolean
  enrolling: boolean
  onEnroll: (cohortId?: string) => Promise<void> | void
}

export function NotEnrolledView({
  course,
  cohorts,
  isOwner,
  isSignedIn,
  enrolling,
  onEnroll,
}: Props) {
  const { t } = useTranslation()
  const [cohortSelectModal, setCohortSelectModal] = useState(false)
  const [selectedCohortId, setSelectedCohortId] = useState<string | null>(null)

  const activeCohort = cohorts.find((c) => c.status === "active")
  const enrollableCohorts = cohorts.filter(isEnrollableCohort)
  const canEnroll = enrollableCohorts.length > 0 || cohorts.length === 0

  const handleEnrollClick = () => {
    if (enrollableCohorts.length === 0) {
      void onEnroll(undefined)
      return
    }
    if (enrollableCohorts.length === 1) {
      const first = enrollableCohorts[0]
      if (first) void onEnroll(first.id)
      return
    }
    const first = enrollableCohorts[0]
    if (first) setSelectedCohortId(first.id)
    setCohortSelectModal(true)
  }

  const confirmCohort = () => {
    if (!selectedCohortId) return
    setCohortSelectModal(false)
    void onEnroll(selectedCohortId)
  }

  return (
    <div className="animate-fade-in container mx-auto px-4 py-6 max-w-3xl">
      <Link to="/">
        <Button variant="ghost" size="sm" className="mb-4 h-8 text-xs">
          <ArrowLeft className="mr-1.5 h-4 w-4" strokeWidth={1.75} aria-hidden />
          {t("courseDetail.allCourses")}
        </Button>
      </Link>

      {course.image_url && (
        <div className="mb-6 w-full aspect-[16/9] overflow-hidden rounded-md border bg-muted">
          <img
            src={toProxyImage(course.image_url)}
            alt={course.title}
            loading="lazy"
            decoding="async"
            className="h-full w-full object-cover"
            onError={(e) => {
              ;(e.currentTarget.parentElement as HTMLElement).style.display = "none"
            }}
          />
        </div>
      )}

      <h1 className="mb-3 font-serif text-3xl font-bold tracking-tight text-wrap-safe sm:text-4xl">
        {course.title}
      </h1>

      {course.description && (
        <p className="text-muted-foreground leading-relaxed mb-6 whitespace-pre-line text-wrap-safe">
          {course.description}
        </p>
      )}

      {activeCohort && (
        <Card className="mb-6">
          <CardContent className="py-4">
            <div className="flex items-center gap-2 mb-1">
              <CalendarDays className="h-4 w-4 text-primary" strokeWidth={1.75} aria-hidden />
              <span className="font-medium">{activeCohort.name}</span>
              <Badge variant={activeCohort.status === "active" ? "success" : "info"}>
                {activeCohort.status}
              </Badge>
            </div>
            <p className="text-sm text-muted-foreground">
              {formatDate(activeCohort.start_date)} &mdash; {formatDate(activeCohort.end_date)}
            </p>
            {activeCohort.enrollment_start && activeCohort.enrollment_end && (
              <p className="text-xs text-muted-foreground mt-1 flex items-center gap-1">
                <Clock className="h-3.5 w-3.5 shrink-0" strokeWidth={1.75} aria-hidden />
                {t("courseDetail.enrollmentRangeLabel", {
                  start: formatDate(activeCohort.enrollment_start),
                  end: formatDate(activeCohort.enrollment_end),
                })}
              </p>
            )}
            {activeCohort.max_students && (
              <p className="text-xs text-muted-foreground mt-1">
                {t("courseDetail.studentsEnrolledOfMax", {
                  enrolled: activeCohort.student_count,
                  max: activeCohort.max_students,
                })}
              </p>
            )}
          </CardContent>
        </Card>
      )}

      {!activeCohort &&
        cohorts.length === 0 &&
        (course.enrollment_start || course.enrollment_end) && (
          <div className="flex flex-wrap items-center gap-2 text-sm mb-6">
            <CalendarDays className="h-4 w-4 shrink-0 text-muted-foreground" strokeWidth={1.75} aria-hidden />
            {course.enrollment_start && course.enrollment_end && (
              <span className="text-muted-foreground text-xs">
                {t("courseDetail.enrollmentRangeLabel", {
                  start: formatDate(course.enrollment_start),
                  end: formatDate(course.enrollment_end),
                })}
              </span>
            )}
          </div>
        )}

      <div>
        {isOwner ? (
          // Owner / admin: show BOTH "Manage Course" (primary, what they
          // usually want) AND "Enroll in Course" so they can preview the
          // course as a student or take their own quizzes. Issue #88
          // surfaced the prior conditional that hid Enroll from owners.
          <div className="flex flex-wrap items-center gap-3">
            <Link to={`/teacher/courses/${course.id}`}>
              <Button size="lg" className="bg-cta-glow">
                {t("courseDetail.manageCourse")}
              </Button>
            </Link>
            <Button
              onClick={handleEnrollClick}
              disabled={enrolling || !canEnroll}
              size="lg"
              variant="outline"
            >
              <Users className="mr-2 h-4 w-4" strokeWidth={1.75} aria-hidden />
              {!canEnroll
                ? t("courseDetail.enrollmentNotAvailable")
                : enrolling
                  ? t("courseDetail.enrolling")
                  : t("courseDetail.enrollInCourse")}
            </Button>
          </div>
        ) : isSignedIn ? (
          <div>
            <Button
              onClick={handleEnrollClick}
              disabled={enrolling || !canEnroll}
              size="lg"
              className={!canEnroll ? undefined : "bg-cta-glow"}
            >
              <Users className="mr-2 h-4 w-4" strokeWidth={1.75} aria-hidden />
              {!canEnroll
                ? t("courseDetail.enrollmentNotAvailable")
                : enrolling
                  ? t("courseDetail.enrolling")
                  : t("courseDetail.enrollInCourse")}
            </Button>
            {!canEnroll && (
              <p className="text-sm text-muted-foreground mt-2">
                {cohorts.length > 0
                  ? t("courseDetail.enrollmentClosedAllCohorts")
                  : t("courseDetail.noCohortsAvailable")}
              </p>
            )}
          </div>
        ) : (
          <Link to="/login">
            <Button size="lg" className="bg-cta-glow">
              {t("courseDetail.signInToEnroll")}
            </Button>
          </Link>
        )}
      </div>

      <CohortSelectModal
        open={cohortSelectModal}
        onClose={() => setCohortSelectModal(false)}
        cohorts={enrollableCohorts}
        selectedCohortId={selectedCohortId}
        onSelect={setSelectedCohortId}
        onConfirm={confirmCohort}
        enrolling={enrolling}
      />
    </div>
  )
}
