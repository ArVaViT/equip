import { useTranslation } from "react-i18next"
import { Link } from "react-router-dom"
import { Card, CardContent } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { EmptyState, ErrorState, Eyebrow } from "@/components/patterns"
import { coursesService } from "@/services/courses"
import type { Certificate, Enrollment } from "@/types"
import { Award, ArrowLeft, RefreshCw, ScrollText } from "lucide-react"
import { Skeleton } from "@/components/ui/skeleton"
import { formatDateLong } from "@/i18n/format"
import { useUserTour } from "@/hooks/useUserTour"
import { useAsyncData } from "@/hooks/useAsyncData"
import { certificatesSteps } from "@/lib/tourSteps"

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

  const courseTitle = (courseId: string | null) => {
    if (!courseId) return t("certificates.courseFallback", { id: "—" })
    const enrollment = enrollments.find((e) => e.course_id === courseId)
    return (
      enrollment?.course?.title ??
      t("certificates.courseFallback", { id: `${courseId.slice(0, 8)}…` })
    )
  }

  if (loading) {
    return <CertificatesPageSkeleton />
  }

  return (
    <div className="container mx-auto px-4 py-8 max-w-5xl">
      <Link to="/courses">
        <Button variant="ghost" size="sm" className="mb-6 h-8 text-xs">
          <ArrowLeft className="h-3.5 w-3.5 mr-1.5" strokeWidth={1.75} />
          {t("certificates.backToCourses")}
        </Button>
      </Link>

      <header data-tour="certs-header" className="mb-10">
        <p className="mb-2 text-xs font-medium uppercase tracking-[0.18em] text-ink-muted">
          {t("certificates.eyebrow")}
        </p>
        <h1 className="font-serif text-3xl font-semibold tracking-tight sm:text-4xl">
          {t("certificates.title")}
        </h1>
        {certificates.length > 0 && (
          <p className="mt-2 text-sm text-ink-muted">
            {t("certificates.subtitle", { count: certificates.length })}
          </p>
        )}
      </header>

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
                    <span className="text-xs font-medium uppercase tracking-[0.18em] text-ink-muted/80">
                      {t("certificates.badge")}
                    </span>
                  </div>

                  <h3 className="mb-4 line-clamp-2 font-serif text-lg font-semibold leading-snug tracking-tight transition-colors group-hover:text-brand">
                    {courseTitle(cert.course_id)}
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
    </div>
  )
}

/**
 * Loading placeholder. Mirrors the final layout (back-button, page header,
 * 1×3 grid of certificate cards) so the page doesn't reflow on data arrival.
 */
function CertificatesPageSkeleton() {
  return (
    <div className="container mx-auto px-4 py-8 max-w-5xl" aria-busy="true">
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
    </div>
  )
}
