import { useState, useRef, useEffect } from "react"
import { Card, CardContent } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { coursesService } from "@/services/courses"
import { useAuth } from "@/context/useAuth"
import { toast } from "@/lib/toast"
import type { Certificate } from "@/types"
import { Award, Copy, CheckCircle, Sparkles, Clock, XCircle, RefreshCw, Star } from "lucide-react"
import { formatDate } from "@/i18n/format"

interface Props {
  courseId: string
  progress: number
  certificate: Certificate | null
  onCertificateUpdate: (cert: Certificate | null) => void
  onReviewSubmitted?: () => void
}

export default function CertificateCard({ courseId, progress, certificate, onCertificateUpdate, onReviewSubmitted }: Props) {
  const { user } = useAuth()
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
      toast({ title: "Please select a rating", variant: "destructive" })
      return
    }
    setReviewSubmitting(true)
    try {
      await coursesService.submitReview(courseId, {
        rating: reviewRating,
        comment: reviewComment || undefined,
      })
      toast({ title: "Review submitted!", variant: "success" })
      setReviewDone(true)
      onReviewSubmitted?.()
    } catch {
      toast({ title: "Failed to submit review", variant: "destructive" })
    } finally {
      setReviewSubmitting(false)
    }
  }

  const handleRequest = async () => {
    setRequesting(true)
    try {
      const cert = await coursesService.requestCertificate(courseId)
      onCertificateUpdate(cert)
      toast({ title: "Certificate requested!", variant: "success" })
    } catch {
      toast({ title: "Failed to request certificate", variant: "destructive" })
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
      toast({ title: "Failed to copy", variant: "destructive" })
    }
  }

  if (progress < 100) return null

  if (!certificate) {
    return (
      <Card className="border-dashed border-l-[3px] border-l-accent">
        <CardContent className="py-6">
          <div className="flex items-center gap-4">
            <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-md bg-muted">
              <Award className="h-6 w-6 text-muted-foreground" />
            </div>
            <div className="flex-1">
              <h3 className="font-serif text-base font-semibold">
                You completed this course
              </h3>
              <p className="mt-0.5 text-sm text-muted-foreground">
                Request your certificate of completion for review.
              </p>
            </div>
            <Button onClick={handleRequest} disabled={requesting}>
              <Sparkles className="mr-1.5 h-4 w-4" />
              {requesting ? "Requesting..." : "Request Certificate"}
            </Button>
          </div>
        </CardContent>
      </Card>
    )
  }

  if (certificate.status === "pending") {
    return (
      <Card className="border-l-[3px] border-l-warning">
        <CardContent className="py-6">
          <div className="flex items-center gap-4">
            <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-md bg-warning/10">
              <Clock className="h-6 w-6 animate-pulse text-warning" />
            </div>
            <div className="flex-1">
              <h3 className="font-serif text-base font-semibold">Awaiting teacher approval</h3>
              <p className="mt-0.5 text-sm text-muted-foreground">
                Your certificate request has been submitted. Your instructor will review it shortly.
              </p>
            </div>
          </div>
        </CardContent>
      </Card>
    )
  }

  if (certificate.status === "teacher_approved") {
    return (
      <Card className="border-l-[3px] border-l-info">
        <CardContent className="py-6">
          <div className="flex items-center gap-4">
            <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-md bg-info/10">
              <Clock className="h-6 w-6 animate-pulse text-info" />
            </div>
            <div className="flex-1">
              <h3 className="font-serif text-base font-semibold">Awaiting admin approval</h3>
              <p className="mt-0.5 text-sm text-muted-foreground">
                Your teacher has approved your certificate. It is now pending final admin approval.
              </p>
            </div>
          </div>
        </CardContent>
      </Card>
    )
  }

  if (certificate.status === "approved") {
    return (
      <Card className="border-l-[3px] border-l-accent">
        <CardContent className="space-y-5 py-6">
          <div className="flex items-start gap-4">
            <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-md bg-accent/15">
              <Award className="h-6 w-6 text-accent" />
            </div>
            <div className="min-w-0 flex-1 space-y-3">
              <div>
                <div className="mb-1 flex items-center gap-2">
                  <h3 className="font-serif text-lg font-semibold">Certificate approved</h3>
                  <Sparkles className="h-4 w-4 text-accent" />
                </div>
                <p className="text-sm text-muted-foreground">
                  Congratulations! Your certificate has been approved.
                </p>
              </div>

              <div className="flex flex-wrap items-center gap-4">
                <div>
                  <p className="mb-0.5 text-xs text-muted-foreground">Certificate number</p>
                  <div className="flex items-center gap-2">
                    <code className="select-all rounded border border-border bg-background px-2.5 py-1 font-mono text-sm">
                      {certificate.certificate_number}
                    </code>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-7 w-7 p-0"
                      onClick={handleCopy}
                      aria-label="Copy certificate number"
                    >
                      {copied ? (
                        <CheckCircle className="h-3.5 w-3.5 text-success" />
                      ) : (
                        <Copy className="h-3.5 w-3.5" />
                      )}
                    </Button>
                  </div>
                </div>
                <div>
                  <p className="mb-0.5 text-xs text-muted-foreground">Issue date</p>
                  <p className="text-sm font-medium">
                    {certificate.issued_at
                      ? formatDate(certificate.issued_at, {
                          year: "numeric",
                          month: "long",
                          day: "numeric",
                        })
                      : "Pending"}
                  </p>
                </div>
              </div>
            </div>
          </div>

          {user && !reviewDone && (
            <div className="space-y-3 border-t border-border pt-5">
              <h4 className="text-sm font-medium">How was this course? Leave a review</h4>
              <div className="flex items-center gap-1">
                {[1, 2, 3, 4, 5].map((value) => (
                  <button
                    key={value}
                    type="button"
                    onClick={() => setReviewRating(value)}
                    onMouseEnter={() => setReviewHover(value)}
                    onMouseLeave={() => setReviewHover(0)}
                    className="transition-transform hover:scale-110 focus:outline-none"
                    aria-label={`Rate ${value} out of 5`}
                  >
                    <Star
                      className={`h-6 w-6 transition-colors ${
                        value <= (reviewHover || reviewRating)
                          ? "fill-warning text-warning"
                          : "text-muted-foreground/30"
                      }`}
                    />
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
                placeholder="Share your thoughts about this course... (optional)"
                rows={3}
                className="flex min-h-[80px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              />
              <Button onClick={handleReviewSubmit} disabled={reviewSubmitting} size="sm">
                {reviewSubmitting ? "Submitting..." : "Submit Review"}
              </Button>
            </div>
          )}

          {reviewDone && (
            <div className="flex items-center gap-2 border-t border-border pt-4 text-sm text-success">
              <CheckCircle className="h-4 w-4" />
              Thank you for your review!
            </div>
          )}
        </CardContent>
      </Card>
    )
  }

  if (certificate.status === "rejected") {
    return (
      <Card className="border-l-[3px] border-l-destructive">
        <CardContent className="py-6">
          <div className="flex items-center gap-4">
            <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-md bg-destructive/10">
              <XCircle className="h-6 w-6 text-destructive" />
            </div>
            <div className="flex-1">
              <h3 className="font-serif text-base font-semibold">
                Certificate request was not approved
              </h3>
              <p className="mt-0.5 text-sm text-muted-foreground">
                Unfortunately, your certificate request was rejected. You may re-request after
                addressing any outstanding requirements.
              </p>
            </div>
            <Button onClick={handleRequest} disabled={requesting} variant="outline">
              <RefreshCw className="mr-1.5 h-4 w-4" />
              {requesting ? "Requesting..." : "Re-request"}
            </Button>
          </div>
        </CardContent>
      </Card>
    )
  }

  return null
}
