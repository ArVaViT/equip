import { useEffect, useState, useCallback } from "react"
import { useTranslation } from "react-i18next"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { coursesService } from "@/services/courses"
import { useAuth } from "@/context/useAuth"
import { toast } from "@/lib/toast"
import type { CourseReview } from "@/types"
import { Star, Trash2, MessageSquare } from "lucide-react"
import PageSpinner from "@/components/ui/PageSpinner"
import { formatDate } from "@/i18n/format"

interface Props {
  courseId: string
}

export default function CourseReviews({ courseId }: Props) {
  const { user } = useAuth()
  const { t } = useTranslation()
  const [reviews, setReviews] = useState<CourseReview[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState(false)
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null)
  const [deletingId, setDeletingId] = useState<string | null>(null)

  const loadReviews = useCallback(async (signal?: { cancelled: boolean }) => {
    setLoading(true)
    setLoadError(false)
    try {
      const data = await coursesService.getCourseReviews(courseId)
      if (signal?.cancelled) return
      setReviews(data)
    } catch {
      if (signal?.cancelled) return
      setLoadError(true)
      toast({ title: t("reviews.loadFailed"), variant: "destructive" })
    } finally {
      if (!signal?.cancelled) setLoading(false)
    }
  }, [courseId, t])

  useEffect(() => {
    const signal = { cancelled: false }
    loadReviews(signal)
    return () => { signal.cancelled = true }
  }, [loadReviews])

  const avgRating =
    reviews.length > 0
      ? reviews.reduce((sum, r) => sum + r.rating, 0) / reviews.length
      : 0

  const handleDelete = async (reviewId: string) => {
    if (deletingId) return
    setDeletingId(reviewId)
    try {
      await coursesService.deleteReview(reviewId)
      setReviews((prev) => prev.filter((r) => r.id !== reviewId))
      setConfirmDeleteId(null)
      toast({ title: t("reviews.deleted"), variant: "success" })
    } catch {
      toast({ title: t("reviews.deleteFailed"), variant: "destructive" })
    } finally {
      setDeletingId(null)
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg flex items-center gap-2">
          <MessageSquare className="h-5 w-5" strokeWidth={1.75} />
          {t("reviews.heading")}
          {reviews.length > 0 && (
            <span className="text-sm font-normal text-muted-foreground ml-1">
              ({reviews.length})
            </span>
          )}
        </CardTitle>
        {reviews.length > 0 && (
          <div className="flex items-center gap-2 mt-2">
            <StarDisplay rating={avgRating} size="lg" />
            <span className="text-sm font-medium">{avgRating.toFixed(1)}</span>
            <span className="text-xs text-muted-foreground">
              {t("reviews.outOf5")} · {t("reviews.reviewCount", { count: reviews.length })}
            </span>
          </div>
        )}
      </CardHeader>
      <CardContent className="space-y-6">
        {loading ? (
          <PageSpinner variant="section" />
        ) : loadError ? (
          <div className="flex flex-col items-center gap-2 py-8">
            <p className="text-sm text-muted-foreground">{t("reviews.loadFailedInline")}</p>
            <Button variant="outline" size="sm" onClick={() => loadReviews()}>
              {t("reviews.retry")}
            </Button>
          </div>
        ) : reviews.length === 0 ? (
          <p className="text-sm text-muted-foreground text-center py-8">
            {t("reviews.empty")}
          </p>
        ) : (
          <div className="space-y-4">
            {reviews.map((review) => (
              <div key={review.id} className="border rounded-lg p-4 space-y-2">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <StarDisplay rating={review.rating} />
                    <span className="text-sm font-medium">
                      {review.reviewer_name || t("reviews.anonymous")}
                    </span>
                  </div>
                  <div className="flex items-center gap-1">
                    <span className="text-xs text-muted-foreground">
                      {formatDate(review.created_at)}
                    </span>
                    {review.user_id === user?.id && (
                      confirmDeleteId === review.id ? (
                        <div className="flex items-center gap-1">
                          <span className="text-xs text-muted-foreground">{t("reviews.confirmDeletePrefix")}</span>
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-6 px-2 text-xs text-destructive hover:text-destructive"
                            disabled={deletingId === review.id}
                            onClick={() => handleDelete(review.id)}
                          >
                            {deletingId === review.id ? t("reviews.confirmDeleteLoading") : t("reviews.confirmDeleteYes")}
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-6 px-2 text-xs"
                            disabled={deletingId === review.id}
                            onClick={() => setConfirmDeleteId(null)}
                          >
                            {t("reviews.confirmDeleteNo")}
                          </Button>
                        </div>
                      ) : (
                        <Button
                          variant="ghost"
                          size="sm"
                          className="h-7 w-7 p-0 text-destructive hover:text-destructive"
                          onClick={() => setConfirmDeleteId(review.id)}
                          aria-label={t("reviews.deleteAria")}
                        >
                          <Trash2 className="h-3.5 w-3.5" strokeWidth={1.75} />
                        </Button>
                      )
                    )}
                  </div>
                </div>
                {review.comment && (
                  <p className="text-sm leading-relaxed text-muted-foreground text-wrap-safe whitespace-pre-line">
                    {review.comment}
                  </p>
                )}
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  )
}

function StarDisplay({ rating, size = "sm" }: { rating: number; size?: "sm" | "lg" }) {
  const iconClass = size === "lg" ? "h-5 w-5" : "h-4 w-4"

  return (
    <div className="flex items-center gap-0.5">
      {[1, 2, 3, 4, 5].map((value) => {
        const filled = value <= Math.round(rating)
        return (
          <Star
            key={value}
            className={`${iconClass} ${
              filled
                ? "fill-warning text-warning"
                : "text-muted-foreground/30"
            }`}
          strokeWidth={1.75} />
        )
      })}
    </div>
  )
}
