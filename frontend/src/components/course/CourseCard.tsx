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

// Distill access mode + enrollment window into one (label, tone) tuple.
// ``institute`` shadows the enrollment-window check — invitation-only
// courses don't surface a public window, and showing both would
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

// Dot + colored label = status indicator (Linear / Vercel). The filled
// ``<Badge>`` variant read as a marketing tag (Sale / New / Featured)
// in the previous revision; this is the modern equivalent.
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
      <Card
        className={
          // Vertical on mobile (cover-then-text, like every other card),
          // horizontal on sm+ (cover-left, text-right, magazine listing).
          // The horizontal layout is what stops the page from reading as
          // a product grid — at sm+ widths each card has the proportions
          // of a book in a catalogue rather than a tile in a marketplace.
          "flex h-full flex-col overflow-hidden hover:border-primary/40 sm:flex-row"
        }
      >
        {/* Cover: 21:9 strip on mobile (so the type below gets the
            weight), 4:3 square-ish panel on sm+ (anchors the listing
            from the left without taking more than ~38% of the row).
            Image-less state uses a gradient + brand-tinted icon so it
            reads as designed, not missing. */}
        <div
          className={
            "aspect-[21/9] w-full overflow-hidden bg-gradient-to-br from-muted to-muted/40 " +
            "sm:aspect-auto sm:h-full sm:w-[38%] sm:max-w-[260px] sm:flex-shrink-0"
          }
        >
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
            <div className="flex h-full min-h-32 w-full items-center justify-center">
              <BookOpen
                className="h-10 w-10 text-primary/25"
                strokeWidth={1.5}
                aria-hidden
              />
            </div>
          )}
        </div>

        {/* Body. p-6 (deviates from the DESIGN.md p-5 default
            deliberately) because the horizontal layout gives the text
            column more horizontal room and the rhythm needs vertical
            breathing to match — without it the title and description
            crowd together against the cover edge. */}
        <div className="flex flex-1 flex-col gap-3 p-6">
          {/* Eyebrow: module count, uppercase tracked. Per DESIGN.md the
              wide tracking is load-bearing — that's what makes it read
              as an editorial label rather than a shrunk body line. */}
          <p className="text-xs font-medium uppercase tracking-[0.18em] text-muted-foreground">
            {t("courseCard.modulesLabel", { count: moduleCount })}
          </p>

          {/* Title: text-2xl Fraunces medium with tight leading and
              negative tracking — confident editorial headline. Smaller
              weights / sizes read as a subhead under the image; heavier
              weights tip Fraunces into "marketing display". Medium at
              2xl is the calibrated point. */}
          <h3 className="font-serif text-2xl font-medium leading-[1.15] tracking-tight text-foreground line-clamp-2 text-wrap-safe">
            {course.title}
          </h3>

          {course.description && (
            <p className="text-[15px] leading-relaxed text-muted-foreground line-clamp-3 text-wrap-safe">
              {course.description}
            </p>
          )}

          {/* Status anchors the bottom of the body. mt-auto pins it
              against the lower edge so it lines up across cards
              regardless of title or description length. When there's no
              status the row collapses entirely. */}
          {status && (
            <div className="mt-auto pt-3">
              <StatusIndicator status={status} />
            </div>
          )}
        </div>
      </Card>
    </Link>
  )
}

export default memo(CourseCard)
