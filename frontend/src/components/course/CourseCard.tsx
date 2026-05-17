import { useState, memo } from "react"
import { Link } from "react-router-dom"
import { useTranslation } from "react-i18next"
import type { TFunction } from "i18next"
import { Card } from "@/components/ui/card"
import type { Course } from "@/types"
import { BookOpen } from "lucide-react"
import { toProxyImage } from "@/lib/images"
import { formatDate } from "@/i18n/format"

interface CourseCardProps {
  course: Course
  style?: React.CSSProperties
}

type StatusKind = "open" | "opens" | "closed" | "institute"
interface Status {
  kind: StatusKind
  label: string
}

// (label, tone) resolution for the inline status indicator.
// ``institute`` shadows the enrollment-window check — invitation-only
// courses don't surface a public window, and showing one would
// mis-signal "anyone can enroll if they hurry".
function resolveStatus(course: Course, t: TFunction): Status | null {
  if (course.access_mode === "institute") {
    return { kind: "institute", label: t("courseCard.byInvitation") }
  }
  const start = course.enrollment_start
  const end = course.enrollment_end
  if (!start && !end) return null
  const now = Date.now()
  if (start && new Date(start).getTime() > now) {
    return { kind: "opens", label: t("courseCard.opensOn", { date: formatDate(new Date(start)) }) }
  }
  if (end && new Date(end).getTime() < now) {
    return { kind: "closed", label: t("courseCard.enrollmentClosed") }
  }
  return { kind: "open", label: t("courseCard.enrollingNow") }
}

const STATUS_TONE: Record<StatusKind, { dot: string; text: string }> = {
  open: { dot: "bg-success", text: "text-success" },
  opens: { dot: "bg-info", text: "text-info" },
  closed: { dot: "bg-destructive", text: "text-destructive" },
  institute: { dot: "bg-muted-foreground/60", text: "text-muted-foreground" },
}

function StatusIndicator({ status }: { status: Status }) {
  const tone = STATUS_TONE[status.kind]
  return (
    <span className="inline-flex items-center gap-1.5 text-xs">
      <span className={`h-1.5 w-1.5 rounded-full ${tone.dot}`} aria-hidden />
      <span className={tone.text}>{status.label}</span>
    </span>
  )
}

function CourseCard({ course, style }: CourseCardProps) {
  const { t } = useTranslation()
  const [imgError, setImgError] = useState(false)
  const coverSrc = toProxyImage(course.image_url)
  const moduleCount = course.modules?.length ?? 0
  const hasImage = !!coverSrc && !imgError
  const status = resolveStatus(course, t)

  return (
    <Link
      to={`/courses/${course.id}`}
      style={style}
      className="group block rounded-md outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
    >
      {/* Catalog row, not a tile. Compact horizontal layout (Vercel
          projects / Linear issues / GitHub repos shape) so the page
          reads as part of the system rather than a wall of marketing
          banners. The previous full-bleed cover was the "ad" tell —
          a 56px thumbnail anchors the row without competing with the
          title. */}
      <Card className="flex h-full items-stretch gap-4 p-4 hover:border-primary/40 sm:items-center sm:gap-5">
        {/* Thumbnail: small enough that vivid cover colours don't
            dominate the page. ``rounded-md`` ties it to the card. The
            empty-state gradient + brand-tinted icon keeps the
            anchor consistent across cards with and without cover art. */}
        <div className="h-14 w-14 shrink-0 overflow-hidden rounded-md bg-gradient-to-br from-muted to-muted/40 sm:h-16 sm:w-16">
          {hasImage ? (
            <img
              src={coverSrc}
              alt={course.title}
              loading="lazy"
              decoding="async"
              className="h-full w-full object-cover"
              onError={() => setImgError(true)}
            />
          ) : (
            <div className="flex h-full w-full items-center justify-center">
              <BookOpen className="h-6 w-6 text-primary/30" strokeWidth={1.5} aria-hidden />
            </div>
          )}
        </div>

        {/* Main column. Title first (Inter medium — system sans, not
            display serif; matches the rest of the dashboard), then a
            single line of description, then the meta row with module
            count and the status indicator. ``min-w-0`` so ``flex-1``
            actually respects the line-clamp on long titles. */}
        <div className="flex min-w-0 flex-1 flex-col gap-1">
          <h3 className="text-base font-medium leading-snug text-foreground line-clamp-1 text-wrap-safe">
            {course.title}
          </h3>
          {course.description && (
            <p className="text-sm leading-relaxed text-muted-foreground line-clamp-1 text-wrap-safe">
              {course.description}
            </p>
          )}
          <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
            <span>{t("courseCard.modulesLabel", { count: moduleCount })}</span>
            {status && (
              <>
                <span aria-hidden className="text-muted-foreground/40">·</span>
                <StatusIndicator status={status} />
              </>
            )}
          </div>
        </div>
      </Card>
    </Link>
  )
}

export default memo(CourseCard)
