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

type StatusKind = "open" | "opens" | "closed" | "institute" | null
interface Status {
  kind: Exclude<StatusKind, null>
  label: string
}

// Distill the access mode + enrollment window into one (label, tone) tuple
// so the render path doesn't carry a conditional ladder. ``institute``
// suppresses the enrollment-window check — invitation-only courses don't
// expose a public window, and showing both would mis-signal "anyone can
// enroll if they hurry".
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

// Dot + colored label instead of a filled pill. The filled-pill variant
// reads as a marketing tag (Sale, New, etc.); dot + label reads as a
// status indicator -- the modern Linear / Vercel pattern. Tones map
// 1:1 to our semantic CSS tokens so dark-mode parity is automatic.
const STATUS_TONE: Record<Status["kind"], { dot: string; text: string }> = {
  open: { dot: "bg-success", text: "text-success" },
  opens: { dot: "bg-info", text: "text-info" },
  closed: { dot: "bg-destructive", text: "text-destructive" },
  institute: { dot: "bg-muted-foreground/60", text: "text-muted-foreground" },
}

function StatusIndicator({ status }: { status: Status }) {
  const tone = STATUS_TONE[status.kind]
  return (
    <span className="inline-flex items-center gap-1.5">
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
      <Card className="flex h-full flex-col overflow-hidden hover:border-primary/40">
        {/* Cover band. 16:9 keeps the image a header strip, not a hero.
            The gradient on the empty state gives image-less cards a real
            designed surface instead of a flat muted block -- pre-fill
            material was the most "placeholder-y" tell of the old card. */}
        <div className="aspect-[16/9] w-full overflow-hidden bg-gradient-to-br from-muted to-muted/40">
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
                className="h-10 w-10 text-primary/25"
                strokeWidth={1.5}
                aria-hidden
              />
            </div>
          )}
        </div>

        <div className="flex flex-1 flex-col gap-3 p-5">
          {/* text-xl + font-medium on Fraunces: confident headline without
              tipping into "marketing" territory. text-lg (the previous
              size) read as a subhead next to the image and let the page
              feel timid. font-semibold here makes Fraunces too heavy. */}
          <h3 className="font-serif text-xl font-medium leading-snug tracking-tight text-foreground line-clamp-2 text-wrap-safe">
            {course.title}
          </h3>
          {course.description && (
            <p className="text-sm leading-relaxed text-muted-foreground line-clamp-2 text-wrap-safe">
              {course.description}
            </p>
          )}

          {/* Meta row: modules count, middle-dot separator, status as a
              colored dot + label. The whole row is one quiet line that
              sits at the bottom of every card via mt-auto. flex-wrap so
              a long localised status string ("Открывается 5 марта 2026")
              breaks under the modules count rather than getting clipped. */}
          <div className="mt-auto flex flex-wrap items-center gap-x-2 gap-y-1 pt-2 text-xs text-muted-foreground">
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
