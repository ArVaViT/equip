import { useState, memo } from "react"
import { Link } from "react-router-dom"
import { useTranslation } from "react-i18next"
import { Card } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import type { Course } from "@/types"
import { BookOpen } from "lucide-react"
import { toProxyImage } from "@/lib/images"
import { formatDate } from "@/i18n/format"

interface CourseCardProps {
  course: Course
  style?: React.CSSProperties
}

type EnrollmentState = "opens" | "closed" | "open" | null

function enrollmentState(start?: string | null, end?: string | null): { state: EnrollmentState; date?: Date } {
  if (!start && !end) return { state: null }
  const now = new Date()
  const s = start ? new Date(start) : null
  const e = end ? new Date(end) : null
  if (s && now < s) return { state: "opens", date: s }
  if (e && now > e) return { state: "closed" }
  return { state: "open" }
}

// One inline pill that summarises access mode + enrollment window for the
// meta row. Lives below the title (not floating over the cover) so the
// card reads as an editorial listing instead of a marketing tile.
function StatusBadge({ course }: { course: Course }) {
  const { t } = useTranslation()
  if (course.access_mode === "institute") {
    return (
      <Badge variant="muted" className="font-normal">
        {t("courseCard.byInvitation")}
      </Badge>
    )
  }
  const { state, date } = enrollmentState(course.enrollment_start, course.enrollment_end)
  if (!state) return null
  if (state === "opens") {
    return (
      <Badge variant="info" className="font-normal">
        {t("courseCard.opensOn", { date: formatDate(date!) })}
      </Badge>
    )
  }
  if (state === "closed") {
    return (
      <Badge variant="destructive" className="font-normal">
        {t("courseCard.enrollmentClosed")}
      </Badge>
    )
  }
  return (
    <Badge variant="success" className="font-normal">
      {t("courseCard.enrollingNow")}
    </Badge>
  )
}

function CourseCard({ course, style }: CourseCardProps) {
  const { t } = useTranslation()
  const [imgError, setImgError] = useState(false)
  const coverSrc = toProxyImage(course.image_url)
  const moduleCount = course.modules?.length ?? 0
  const hasImage = !!coverSrc && !imgError

  return (
    <Link
      to={`/courses/${course.id}`}
      style={style}
      className="group block rounded-md outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
    >
      <Card className="flex h-full flex-col overflow-hidden hover:border-primary/30">
        {/* Cover strip. 16:9 (slimmer than the old 16:10) so the image
            reads as a header band, not a hero. No hover-zoom — that was
            the loudest "marketing tile" tell. Bg-muted so an image-less
            card still has a calm coloured band of the same height,
            keeping every card in the grid the exact same total height. */}
        <div className="aspect-[16/9] w-full overflow-hidden bg-muted">
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
                className="h-8 w-8 text-muted-foreground/40"
                strokeWidth={1.5}
                aria-hidden
              />
            </div>
          )}
        </div>

        <div className="flex flex-1 flex-col gap-3 p-5">
          <h3 className="font-serif text-lg leading-snug text-foreground line-clamp-2 text-wrap-safe">
            {course.title}
          </h3>
          {course.description && (
            <p className="text-sm leading-relaxed text-muted-foreground line-clamp-2 text-wrap-safe">
              {course.description}
            </p>
          )}

          {/* Meta row pinned to the bottom of the card. mt-auto pushes
              this against the lower edge regardless of title/description
              length, so every card lines up across the grid. The module
              count and the status pill sit on the same baseline; we drop
              the previous "Open course →" CTA because the whole card is
              already a link — the explicit affordance was the second
              loudest "ad" tell. */}
          <div className="mt-auto flex flex-wrap items-center gap-x-3 gap-y-2 pt-2 text-xs text-muted-foreground">
            <span className="inline-flex items-center gap-1.5">
              <BookOpen className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
              {t("courseCard.modulesLabel", { count: moduleCount })}
            </span>
            <StatusBadge course={course} />
          </div>
        </div>
      </Card>
    </Link>
  )
}

export default memo(CourseCard)
