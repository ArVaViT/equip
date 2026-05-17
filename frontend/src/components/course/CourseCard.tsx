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

// (label, tone) resolution for the status eyebrow. ``institute`` shadows
// the enrollment-window check — invitation-only courses don't surface a
// public window, and "Opens Mar 5" on a private course would mis-signal
// "anyone can enroll if they hurry".
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

// Tones map 1:1 to our semantic CSS tokens so dark-mode parity is
// automatic. Dot + label (not a filled pill) so the status reads as a
// status indicator rather than a marketing tag.
const STATUS_TONE: Record<StatusKind, { dot: string; text: string }> = {
  open: { dot: "bg-success", text: "text-success" },
  opens: { dot: "bg-info", text: "text-info" },
  closed: { dot: "bg-destructive", text: "text-destructive" },
  institute: { dot: "bg-muted-foreground/60", text: "text-muted-foreground" },
}

// The status now sits ABOVE the title as an editorial eyebrow — the
// pattern DESIGN.md formalised for VerseOfTheDayCard and
// CourseReadinessCard ("text-xs font-medium uppercase tracking-[0.18em]
// text-muted-foreground"). The wide tracking is load-bearing: that's
// what makes it read as an eyebrow rather than a shrunk body line.
function StatusEyebrow({ status }: { status: Status }) {
  const tone = STATUS_TONE[status.kind]
  return (
    <p
      className={`inline-flex items-center gap-2 text-xs font-medium uppercase tracking-[0.18em] ${tone.text}`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${tone.dot}`} aria-hidden />
      {status.label}
    </p>
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
      <Card className="flex h-full flex-col overflow-hidden hover:border-primary/40">
        {/* Cinematic 21:9 cover band — slimmer than the old 16:10 / 16:9
            so the typography below gets the visual weight. Gradient bg
            on the empty state turns the image-less card from "missing"
            into "designed". */}
        <div className="aspect-[21/9] w-full overflow-hidden bg-gradient-to-br from-muted to-muted/40">
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
              <BookOpen
                className="h-9 w-9 text-primary/25"
                strokeWidth={1.5}
                aria-hidden
              />
            </div>
          )}
        </div>

        <div className="flex flex-1 flex-col gap-4 p-5">
          {/* Status eyebrow above the title. When there's no status (no
              enrollment window, public access mode), nothing reserves
              its row — the title slides up against the cover. */}
          {status && <StatusEyebrow status={status} />}

          {/* The title is the focal point of the card. text-2xl Fraunces
              medium with tight tracking reads as a confident editorial
              headline; the previous text-lg / text-xl sat as a subhead
              under the image. font-semibold on Fraunces is too heavy in
              a list view — medium is the calibrated choice. */}
          <h3 className="font-serif text-2xl font-medium leading-[1.15] tracking-tight text-foreground line-clamp-2 text-wrap-safe">
            {course.title}
          </h3>

          {course.description && (
            <p className="text-[15px] leading-relaxed text-muted-foreground line-clamp-2 text-wrap-safe">
              {course.description}
            </p>
          )}

          {/* Single quiet line at the bottom: modules count only — the
              status is the eyebrow above the title now, no need to
              repeat it here. mt-auto pins this against the lower edge
              so every card aligns across the grid. */}
          <p className="mt-auto pt-2 text-xs text-muted-foreground">
            {t("courseCard.modulesLabel", { count: moduleCount })}
          </p>
        </div>
      </Card>
    </Link>
  )
}

export default memo(CourseCard)
