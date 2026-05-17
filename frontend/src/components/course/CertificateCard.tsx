import { useState, useRef, useEffect } from "react"
import { useTranslation } from "react-i18next"
import { Card, CardContent } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { coursesService } from "@/services/courses"
import { useAuth } from "@/context/useAuth"
import { toast } from "@/lib/toast"
import type { Certificate } from "@/types"
import { Award, Copy, CheckCircle, Sparkles, Clock, XCircle, RefreshCw, Star } from "lucide-react"
import { formatDateLong } from "@/i18n/format"

interface Props {
  courseId: string
  progress: number
  certificate: Certificate | null
  onCertificateUpdate: (cert: Certificate | null) => void
  onReviewSubmitted?: () => void
}

export default function CertificateCard({ courseId, progress, certificate, onCertificateUpdate, onReviewSubmitted }: Props) {
  const { user } = useAuth()
  const { t } = useTranslation()
  const [requesting, setRequesting] = useState(false)
  const [copied, setCopied] = useState(false)
  const copyTimer = useRef<ReturnType<typeof setTimeout>>()

  useEffect(() => {
    return () => clearTimeout(copyTimer.current)
  }, [])
  const [reviewRating, setReviewRating] = useState(0)
  const [reviewHover, setReviewHover] = useState(0)
  const [reviewComment, setReviewComment] = useState("")
  const [reviewSubmitting, setReviewSubmitting] = useState(false)
  const [reviewDone, setReviewDone] = useState(false)

  const handleReviewSubmit = async () => {
    if (reviewRating === 0) {
      toast({ title: t("certificates.card.review.missingRating"), variant: "destructive" })
      return
    }
    setReviewSubmitting(true)
    try {
      await coursesService.submitReview(courseId, {
        rating: reviewRating,
        comment: reviewComment || undefined,
      })
      toast({ title: t("certificates.card.review.submitted"), variant: "success" })
      setReviewDone(true)
      onReviewSubmitted?.()
    } catch {
      toast({ title: t("certificates.card.review.submitFailed"), variant: "destructive" })
    } finally {
      setReviewSubmitting(false)
    }
  }

  const handleRequest = async () => {
    setRequesting(true)
    try {
      const cert = await coursesService.requestCertificate(courseId)
      onCertificateUpdate(cert)
      toast({ title: t("certificates.card.requestSuccess"), variant: "success" })
    } catch {
      toast({ title: t("certificates.card.requestFailed"), variant: "destructive" })
    } finally {
      setRequesting(false)
    }
  }

  const handleCopy = async () => {
    if (!certificate) return
    try {
      await navigator.clipboard.writeText(certificate.certificate_number)
      setCopied(true)
      clearTimeout(copyTimer.current)
      copyTimer.current = setTimeout(() => setCopied(false), 2000)
    } catch {
      toast({ title: t("certificates.card.copyFailed"), variant: "destructive" })
    }
  }

  if (progress < 100) return null

  if (!certificate) {
    return (
      <Card className="border-dashed border-l-stripe border-l-accent">
        <CardContent className="py-6">
          <div className="flex items-center gap-4">
            <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-md bg-muted">
              <Award className="h-6 w-6 text-muted-foreground" strokeWidth={1.75} />
            </div>
            <div className="flex-1">
              <h3 className="font-serif text-base font-semibold">
                {t("certificates.card.completedTitle")}
              </h3>
              <p className="mt-0.5 text-sm text-muted-foreground">
                {t("certificates.card.completedDescription")}
              </p>
            </div>
            <Button onClick={handleRequest} disabled={requesting}>
              <Sparkles className="mr-1.5 h-4 w-4" strokeWidth={1.75} />
              {requesting ? t("certificates.card.requesting") : t("certificates.card.request")}
            </Button>
          </div>
        </CardContent>
      </Card>
    )
  }

  if (certificate.status === "pending") {
    return (
      <Card className="border-l-stripe border-l-warning">
        <CardContent className="py-6">
          <div className="flex items-center gap-4">
            <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-md bg-warning/10">
              <Clock className="h-6 w-6 text-warning" strokeWidth={1.75} aria-hidden="true" />
            </div>
            <div className="flex-1">
              <h3 className="font-serif text-base font-semibold">{t("certificates.card.pendingTitle")}</h3>
              <p className="mt-0.5 text-sm text-muted-foreground">
                {t("certificates.card.pendingDescription")}
              </p>
            </div>
          </div>
        </CardContent>
      </Card>
    )
  }

  if (certificate.status === "teacher_approved") {
    return (
      <Card className="border-l-stripe border-l-info">
        <CardContent className="py-6">
          <div className="flex items-center gap-4">
            <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-md bg-info/10">
              <Clock className="h-6 w-6 text-info" strokeWidth={1.75} aria-hidden="true" />
            </div>
            <div className="flex-1">
              <h3 className="font-serif text-base font-semibold">{t("certificates.card.adminPendingTitle")}</h3>
              <p className="mt-0.5 text-sm text-muted-foreground">
                {t("certificates.card.adminPendingDescription")}
              </p>
            </div>
          </div>
        </CardContent>
      </Card>
    )
  }

  if (certificate.status === "approved") {
    return (
      <Card className="border-l-stripe border-l-accent">
        <CardContent className="space-y-5 py-6">
          <div className="flex items-start gap-4">
            <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-md bg-accent/15">
              <Award className="h-6 w-6 text-accent" strokeWidth={1.75} aria-hidden />
            </div>
            <div className="min-w-0 flex-1 space-y-4">
              <div>
                <p className="mb-1 flex items-center gap-1.5 text-xs font-medium uppercase tracking-[0.18em] text-accent">
                  <Sparkles className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
                  {t("certificates.card.approvedEyebrow")}
                </p>
                <h3 className="font-serif text-xl font-semibold tracking-tight">
                  {t("certificates.card.approvedTitle")}
                </h3>
                <p className="mt-1 text-sm text-muted-foreground">
                  {t("certificates.card.approvedDescription")}
                </p>
              </div>

              <div className="grid gap-4 rounded-md border border-border bg-muted/20 p-4 sm:grid-cols-2">
                <div>
                  <p className="mb-1.5 text-xs font-medium uppercase tracking-[0.18em] text-muted-foreground">
                    {t("certificates.card.certificateNumber")}
                  </p>
                  <div className="flex items-center gap-2">
                    <code className="select-all rounded border border-border bg-background px-2.5 py-1 font-mono text-sm">
                      {certificate.certificate_number}
                    </code>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-7 w-7 p-0"
                      onClick={handleCopy}
                      aria-label={t("certificates.card.copyAria")}
                    >
                      {copied ? (
                        <CheckCircle className="h-3.5 w-3.5 text-success" strokeWidth={1.75} />
                      ) : (
                        <Copy className="h-3.5 w-3.5" strokeWidth={1.75} />
                      )}
                    </Button>
                  </div>
                </div>
                <div>
                  <p className="mb-1.5 text-xs font-medium uppercase tracking-[0.18em] text-muted-foreground">
                    {t("certificates.card.issueDate")}
                  </p>
                  <p className="text-sm font-medium">
                    {certificate.issued_at
                      ? formatDateLong(certificate.issued_at)
                      : t("certificates.card.issuePending")}
                  </p>
                </div>
              </div>
            </div>
          </div>

          {user && !reviewDone && (
            <div className="space-y-3 border-t border-border pt-5">
              <p className="text-xs font-medium uppercase tracking-[0.18em] text-muted-foreground">
                {t("certificates.card.review.eyebrow")}
              </p>
              <h4 className="font-serif text-base font-semibold tracking-tight">{t("certificates.card.review.heading")}</h4>
              <div className="flex items-center gap-1">
                {[1, 2, 3, 4, 5].map((value) => (
                  <button
                    key={value}
                    type="button"
                    onClick={() => setReviewRating(value)}
                    onMouseEnter={() => setReviewHover(value)}
                    onMouseLeave={() => setReviewHover(0)}
                    className="transition-transform hover:scale-110 focus:outline-none"
                    aria-label={t("certificates.card.review.starAria", { value })}
                  >
                    <Star
                      className={`h-6 w-6 transition-colors ${
                        value <= (reviewHover || reviewRating)
                          ? "fill-warning text-warning"
                          : "text-muted-foreground/30"
                      }`}
                    strokeWidth={1.75} />
                  </button>
                ))}
                {reviewRating > 0 && (
                  <span className="ml-2 text-sm text-muted-foreground">
                    {reviewRating}/5
                  </span>
                )}
              </div>
              <textarea
                value={reviewComment}
                onChange={(e) => setReviewComment(e.target.value)}
                placeholder={t("certificates.card.review.commentPlaceholder")}
                rows={3}
                className="flex min-h-[80px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              />
              <Button onClick={handleReviewSubmit} disabled={reviewSubmitting} size="sm">
                {reviewSubmitting ? t("certificates.card.review.submitting") : t("certificates.card.review.submit")}
              </Button>
            </div>
          )}

          {reviewDone && (
            <div className="flex items-center gap-2 border-t border-border pt-4 text-sm text-success">
              <CheckCircle className="h-4 w-4" strokeWidth={1.75} />
              {t("certificates.card.review.thanks")}
            </div>
          )}
        </CardContent>
      </Card>
    )
  }

  if (certificate.status === "rejected") {
    return (
      <Card className="border-l-stripe border-l-destructive">
        <CardContent className="py-6">
          <div className="flex items-center gap-4">
            <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-md bg-destructive/10">
              <XCircle className="h-6 w-6 text-destructive" strokeWidth={1.75} />
            </div>
            <div className="flex-1">
              <h3 className="font-serif text-base font-semibold">
                {t("certificates.card.rejectedTitle")}
              </h3>
              <p className="mt-0.5 text-sm text-muted-foreground">
                {t("certificates.card.rejectedDescription")}
              </p>
            </div>
            <Button onClick={handleRequest} disabled={requesting} variant="outline">
              <RefreshCw className="mr-1.5 h-4 w-4" strokeWidth={1.75} />
              {requesting ? t("certificates.card.requesting") : t("certificates.card.rerequest")}
            </Button>
          </div>
        </CardContent>
      </Card>
    )
  }

  return null
}
