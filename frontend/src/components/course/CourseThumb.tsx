import { useState } from "react"
import { CourseCoverFallback } from "@/components/course/CourseCoverFallback"
import { toProxyImage } from "@/lib/images"
import { cn } from "@/lib/utils"

interface CourseThumbProps {
  course: { id: string; title?: string | null; image_url?: string | null }
  className?: string
}

/**
 * A course's cover at the size of a line of text, for lists that were
 * titles alone — «текст слабо смотрится, добавь маленький тамбнейл с
 * обложкой, но не увеличивай пространство на курс».
 *
 * The cover's own shape (16:10, the 1600×1000 of every cover), not a
 * circle: the covers are typographic — a title, a map, a shelf of spines —
 * and a circle crops exactly the part that tells one from another.
 * 28px tall, which fits inside the rows it goes into without making them
 * taller. Decorative: the title beside it already names the course.
 */
export function CourseThumb({ course, className }: CourseThumbProps) {
  const src = toProxyImage(course.image_url)
  // A cover that fails to load falls back to the monogram rather than to
  // the browser's broken-image glyph.
  const [failed, setFailed] = useState(false)
  return (
    <span
      aria-hidden
      className={cn(
        // The monogram fallback is sized for a card; at 28px it needs
        // to be a letter, not a headline.
        "relative block aspect-[16/10] h-7 shrink-0 overflow-hidden rounded-[5px] bg-muted ring-1 ring-inset ring-black/5 dark:ring-white/10 [&_.course-cover-letter]:text-xs",
        className,
      )}
    >
      {src && !failed ? (
        <img
          src={src}
          alt=""
          loading="lazy"
          decoding="async"
          onError={() => setFailed(true)}
          className="h-full w-full object-cover"
        />
      ) : (
        <CourseCoverFallback courseId={course.id} title={course.title ?? ""} size="sm" />
      )}
    </span>
  )
}
