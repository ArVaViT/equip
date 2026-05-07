import { useState, memo } from "react"
import { Link } from "react-router-dom"
import { useTranslation } from "react-i18next"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import type { Course } from "@/types"
import { BookOpen, ArrowRight } from "lucide-react"
import { toProxyImage } from "@/lib/images"
import { formatDate } from "@/i18n/format"

interface CourseCardProps {
  course: Course
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

function EnrollmentBadge({ start, end }: { start?: string | null; end?: string | null }) {
  const { t } = useTranslation()
  const { state, date } = enrollmentState(start, end)
  if (!state) return null
  if (state === "opens") {
    return (
      <Badge variant="info" className="absolute right-3 top-3 z-10">
        {t("courseCard.opensOn", { date: formatDate(date!) })}
      </Badge>
    )
  }
  if (state === "closed") {
    return (
      <Badge variant="destructive" className="absolute right-3 top-3 z-10">
        {t("courseCard.enrollmentClosed")}
      </Badge>
    )
  }
  return (
    <Badge variant="success" className="absolute right-3 top-3 z-10">
      {t("courseCard.enrollingNow")}
    </Badge>
  )
}

function CourseCard({ course }: CourseCardProps) {
  const { t } = useTranslation()
  const [imgError, setImgError] = useState(false)
  const coverSrc = toProxyImage(course.image_url)
  const moduleCount = course.modules?.length ?? 0

  return (
    <Link
      to={`/courses/${course.id}`}
      className="group block rounded-md outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
    >
      <Card className="flex h-full flex-col overflow-hidden border-border/60 transition-colors hover:border-primary/40">
        <div className="relative">
          <EnrollmentBadge start={course.enrollment_start} end={course.enrollment_end} />
          {coverSrc && !imgError ? (
            <div className="aspect-[16/10] w-full overflow-hidden bg-muted">
              <img
                src={coverSrc}
                alt={course.title}
                loading="lazy"
                decoding="async"
                className="h-full w-full object-cover transition-transform duration-500 group-hover:scale-[1.02]"
                onError={() => setImgError(true)}
              />
            </div>
          ) : (
            <div className="flex aspect-[16/10] w-full items-center justify-center bg-muted">
              <BookOpen className="h-10 w-10 text-muted-foreground/30" strokeWidth={1.75} aria-hidden />
            </div>
          )}
        </div>
        <CardHeader className="pb-2">
          <CardTitle className="font-serif text-lg leading-snug line-clamp-2 text-wrap-safe">
            {course.title}
          </CardTitle>
          {course.description && (
            <CardDescription className="line-clamp-2 text-xs leading-relaxed text-wrap-safe">
              {course.description}
            </CardDescription>
          )}
        </CardHeader>
        <CardContent className="mt-auto flex items-center justify-between pt-2 text-xs text-muted-foreground">
          <span className="uppercase tracking-wide">{t("courseCard.modulesLabel", { count: moduleCount })}</span>
          <span className="inline-flex items-center gap-1 text-foreground/80 transition-colors group-hover:text-primary">
            {t("courseCard.openCourse")}
            <ArrowRight
              className="h-3.5 w-3.5 transition-transform group-hover:translate-x-0.5"
              strokeWidth={1.75}
              aria-hidden
            />
          </span>
        </CardContent>
      </Card>
    </Link>
  )
}

export default memo(CourseCard)
