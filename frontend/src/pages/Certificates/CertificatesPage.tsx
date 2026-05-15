import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { Link } from "react-router-dom"
import { Card, CardContent } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { coursesService } from "@/services/courses"
import type { Certificate, Enrollment } from "@/types"
import { toast } from "@/lib/toast"
import { Award, ArrowLeft, ScrollText } from "lucide-react"
import PageSpinner from "@/components/ui/PageSpinner"
import { formatDateLong } from "@/i18n/format"

export default function CertificatesPage() {
  const { t } = useTranslation()
  const [certificates, setCertificates] = useState<Certificate[]>([])
  const [enrollments, setEnrollments] = useState<Enrollment[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    const load = async () => {
      try {
        const [certs, courses] = await Promise.all([
          coursesService.getMyCertificates(),
          coursesService.getMyCourses().catch(() => []),
        ])
        if (cancelled) return
        setCertificates(certs)
        setEnrollments(courses)
      } catch {
        if (!cancelled) toast({ title: t("toast.certificatesLoadFailed"), variant: "destructive" })
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => {
      cancelled = true
    }
  }, [t])

  const courseTitle = (courseId: string) => {
    const enrollment = enrollments.find((e) => e.course_id === courseId)
    return (
      enrollment?.course?.title ??
      t("certificates.courseFallback", { id: `${courseId.slice(0, 8)}…` })
    )
  }

  if (loading) {
    return <PageSpinner />
  }

  return (
    <div className="container mx-auto px-4 py-8 max-w-5xl">
      <Link to="/">
        <Button variant="ghost" size="sm" className="mb-6 h-8 text-xs">
          <ArrowLeft className="h-3.5 w-3.5 mr-1.5" strokeWidth={1.75} />
          {t("certificates.dashboard")}
        </Button>
      </Link>

      <h1 className="mb-8 flex items-center gap-3 font-serif text-3xl font-bold tracking-tight">
        <div className="flex h-10 w-10 items-center justify-center rounded-md bg-muted">
          <Award className="h-5 w-5 text-muted-foreground" strokeWidth={1.75} />
        </div>
        {t("certificates.title")}
      </h1>

      {certificates.length === 0 ? (
        <Card className="border-dashed">
          <CardContent className="flex flex-col items-center justify-center py-20 text-center">
            <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-muted">
              <ScrollText className="h-8 w-8 text-muted-foreground/50" strokeWidth={1.75} />
            </div>
            <h3 className="mb-1 text-lg font-medium">{t("certificates.emptyTitle")}</h3>
            <p className="mb-6 max-w-sm text-sm text-muted-foreground">
              {t("certificates.emptyDescription")}
            </p>
            <Link to="/">
              <Button size="sm">{t("certificates.browseCourses")}</Button>
            </Link>
          </CardContent>
        </Card>
      ) : (
        <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {certificates.map((cert) => (
            <Card
              key={cert.id}
              className="group relative overflow-hidden border-l-[3px] border-l-accent transition-colors hover:border-primary/40"
            >
              <CardContent className="pb-5 pt-6">
                <div className="mb-4 flex items-start justify-between">
                  <div className="flex h-11 w-11 items-center justify-center rounded-md bg-muted">
                    <Award className="h-5 w-5 text-muted-foreground" strokeWidth={1.75} />
                  </div>
                  <span className="font-mono text-xs uppercase tracking-wider text-muted-foreground/70">
                    {t("certificates.badge")}
                  </span>
                </div>

                <h3 className="mb-3 line-clamp-2 font-serif text-base font-semibold leading-snug transition-colors group-hover:text-primary">
                  {courseTitle(cert.course_id)}
                </h3>

                <dl className="space-y-2 text-xs">
                  {cert.certificate_number && (
                    <div className="flex items-center justify-between">
                      <dt className="text-muted-foreground">{t("certificates.certificateNo")}</dt>
                      <dd className="font-mono font-medium text-foreground">
                        {cert.certificate_number}
                      </dd>
                    </div>
                  )}
                  <div className="flex items-center justify-between">
                    <dt className="text-muted-foreground">
                      {cert.status === "approved" ? t("certificates.issuedOrStatus") : t("certificates.statusColumn")}
                    </dt>
                    <dd className="font-medium">
                      {cert.status === "approved" && cert.issued_at
                        ? formatDateLong(cert.issued_at, { month: "short" })
                        : cert.status === "pending"
                          ? t("certificates.pendingApproval")
                          : cert.status === "teacher_approved"
                            ? t("certificates.awaitingAdmin")
                            : cert.status === "rejected"
                              ? t("certificates.rejected")
                              : t("certificates.pending")}
                    </dd>
                  </div>
                </dl>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}
