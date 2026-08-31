import { useTranslation } from "react-i18next"
import { Link } from "react-router-dom"
import { Card, CardContent } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { EmptyState, ErrorState, Eyebrow, PageHeader } from "@/components/patterns"
import { coursesService } from "@/services/courses"
import { countAwarded } from "@/lib/certificates"
import type { Certificate, Enrollment } from "@/types"
import { Award, ArrowLeft, RefreshCw, ScrollText } from "lucide-react"
import { Skeleton } from "@/components/ui/skeleton"
import { formatDateLong } from "@/i18n/format"
import { useUserTour } from "@/hooks/useUserTour"
import { useAsyncData } from "@/hooks/useAsyncData"
import { certificatesSteps } from "@/lib/tourSteps"
import { Section } from "@/components/layout/Section"

export default function CertificatesPage() {
  const { t, i18n } = useTranslation()
  // ``i18n.language`` in deps so a locale flip re-pulls the
  // localised course-title overlay without a hard reload. We
  // deliberately do NOT include ``t`` — its reference change is
  // implementation-defined across react-i18next versions and using
  // it as a dep was the brittle pattern in this codebase.
  const { data, loading, error, refetch: retry } = useAsyncData(
    async () => {
      const [certs, courses] = await Promise.all([
        coursesService.getMyCertificates(),
        coursesService.getMyCourses().catch(() => [] as Enrollment[]),
      ])
      return { certificates: certs, enrollments: courses }
    },
    [i18n.language],
  )
  const certificates: Certificate[] = data?.certificates ?? []
  const enrollments: Enrollment[] = data?.enrollments ?? []
  // Distinguish load-failure from genuine empty so the user doesn't see
  // "no certificates yet — start learning" when the request actually
  // 500'd. The empty-state copy is a call to action that's wrong (and
  // misleading) when we never knew whether they have any.
  const loadError = error !== null

  useUserTour({
    tourId: "certificates-v1",
    steps: certificatesSteps(t),
    ready: !loading,
  })

  /**
   * What course this certificate is for.
   *
   * Three sources, in order of how much they know:
   *
   * 1. The live course, if the reader is still enrolled in it.
   * 2. ``archived_course_title`` — written onto the certificate when it was
   *    requested, precisely so the name survives the course being deleted.
   *    The page ignored it, so every certificate for a removed course read
   *    "Course —" in the list while ``CertificateDocument`` printed the real
   *    name on the certificate itself. Fourteen rows in production today.
   * 3. The id, as a last resort.
   *
   * ``||`` rather than ``??`` throughout: a course with no title in this
   * reader's language comes back as an empty string, not null, and an empty
   * string went straight onto the row.
   */
  const courseTitle = (cert: Certificate) => {
    const enrollment = cert.course_id
      ? enrollments.find((e) => e.course_id === cert.course_id)
      : undefined
    return (
      enrollment?.course?.title?.trim() ||
      cert.archived_course_title?.trim() ||
      t("certificates.courseFallback", {
        id: cert.course_id ? `${cert.course_id.slice(0, 8)}…` : "—",
      })
    )
  }

  if (loading) {
    return <CertificatesPageSkeleton />
  }

  return (
    <Section>
      <Link to="/courses">
        <Button variant="ghost" size="sm" className="mb-6 h-8 text-xs">
          <ArrowLeft className="h-3.5 w-3.5 mr-1.5" strokeWidth={1.75} />
          {t("certificates.backToCourses")}
        </Button>
      </Link>

      <PageHeader
        data-tour="certs-header"
        eyebrow={t("certificates.eyebrow")}
        title={t("certificates.title")}
        description={
          certificates.length > 0
            ? // Only the ones actually awarded. The page used to count every
              // row, so a reader whose fourteen requests had all been
              // rejected was told "14 certificates earned" above fourteen
              // cards each saying "Rejected".
              t("certificates.subtitle", {
                count: countAwarded(certificates),
              })
            : undefined
        }
      />

      {loadError ? (
        <ErrorState
          title={t("toast.certificatesLoadFailed")}
          description={t("certificates.loadErrorDescription")}
          action={
            <Button size="sm" onClick={retry}>
              <RefreshCw className="mr-1.5 h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
              {t("common.tryAgain")}
            </Button>
          }
        />
      ) : certificates.length === 0 ? (
        <EmptyState
          icon={<ScrollText strokeWidth={1.75} aria-hidden />}
          title={t("certificates.emptyTitle")}
          description={t("certificates.emptyDescription")}
          action={
            <Link to="/courses">
              <Button size="sm">{t("certificates.browseCourses")}</Button>
            </Link>
          }
        />
      ) : (
        <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {certificates.map((cert) => {
            const isApproved = cert.status === "approved"
            const statusLabel = isApproved && cert.issued_at
              ? formatDateLong(cert.issued_at, { month: "short" })
              : cert.status === "pending"
                ? t("certificates.pendingApproval")
                : cert.status === "teacher_approved"
                  ? t("certificates.awaitingAdmin")
                  : cert.status === "rejected"
                    ? t("certificates.rejected")
                    : t("certificates.pending")
            return (
              <Card
                key={cert.id}
                className={`group relative flex flex-col overflow-hidden border-l-stripe transition-colors ${
                  isApproved
                    ? "border-l-accent hover:border-brand/40"
                    : "border-l-muted-foreground/30"
                }`}
              >
                <CardContent className="flex flex-1 flex-col px-5 pb-5 pt-6">
                  <div className="mb-5 flex items-start justify-between">
                    <div className={`flex h-11 w-11 items-center justify-center rounded-md ${
                      isApproved ? "bg-accent/15" : "bg-muted"
                    }`}>
                      <Award
                        className={`h-5 w-5 ${isApproved ? "text-accent" : "text-ink-muted"}`}
                        strokeWidth={1.75}
                        aria-hidden
                      />
                    </div>
                    <span className="text-xs font-medium uppercase tracking-[0.18em] text-ink-muted">
                      {t("certificates.badge")}
                    </span>
                  </div>

                  <h3 className="mb-4 line-clamp-2 font-serif text-lg font-semibold leading-snug tracking-tight transition-colors group-hover:text-brand">
                    {courseTitle(cert)}
                  </h3>

                  <div className="mt-auto space-y-3 border-t border-edge pt-3 text-xs">
                    {cert.certificate_number && (
                      <div>
                        <p className="text-xs font-medium uppercase tracking-[0.18em] text-ink-muted">
                          {t("certificates.certificateNo")}
                        </p>
                        <p className="mt-0.5 select-all font-mono text-sm font-medium text-ink">
                          {cert.certificate_number}
                        </p>
                      </div>
                    )}
                    <div>
                      <Eyebrow>
                        {isApproved ? t("certificates.issuedOrStatus") : t("certificates.statusColumn")}
                      </Eyebrow>
                      <p className={`mt-0.5 text-sm font-medium ${isApproved ? "text-ink" : "text-ink-muted"}`}>
                        {statusLabel}
                      </p>
                    </div>
                    {isApproved && (
                      // The row exists to lead here. A certificate that can only
                      // be read as a list item is not a certificate.
                      <Link to={`/certificates/${cert.id}`} className="block pt-1">
                        <Button size="sm" variant="outline" className="w-full">
                          <ScrollText className="mr-1.5 h-4 w-4" strokeWidth={1.75} aria-hidden />
                          {t("certificates.document.open")}
                        </Button>
                      </Link>
                    )}
                  </div>
                </CardContent>
              </Card>
            )
          })}
        </div>
      )}
    </Section>
  )
}

/**
 * Loading placeholder. Mirrors the final layout (back-button, page header,
 * 1×3 grid of certificate cards) so the page doesn't reflow on data arrival.
 */
function CertificatesPageSkeleton() {
  return (
    <Section aria-busy="true">
      <Skeleton className="mb-6 h-7 w-32" />
      <div className="mb-10 space-y-2">
        <Skeleton className="h-3 w-24" />
        <Skeleton className="h-9 w-64" />
        <Skeleton className="h-4 w-40" />
      </div>
      <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <Card key={i}>
            <CardContent className="px-5 pb-5 pt-6">
              <div className="mb-5 flex items-start justify-between">
                <Skeleton className="h-11 w-11 rounded-md" />
                <Skeleton className="h-3 w-16" />
              </div>
              <Skeleton className="mb-2 h-5 w-3/4" />
              <Skeleton className="mb-5 h-5 w-1/2" />
              <div className="space-y-2 border-t border-edge pt-3">
                <Skeleton className="h-3 w-20" />
                <Skeleton className="h-4 w-2/3" />
                <Skeleton className="h-3 w-20 mt-2" />
                <Skeleton className="h-4 w-1/2" />
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </Section>
  )
}
