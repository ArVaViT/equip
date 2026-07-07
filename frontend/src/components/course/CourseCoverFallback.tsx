import { useMemo } from "react"
import { cn } from "@/lib/utils"

interface CourseCoverFallbackProps {
  /** Course id — hashed to deterministically pick one of the five tint
   *  variants, so the same course always renders the same cover. */
  courseId: string
  title: string
  /** Controls the monogram scale. ``sm`` for small list thumbnails
   *  (teacher dashboard row), ``md`` for catalog/dashboard grid cards,
   *  ``lg`` for full-width hero covers (course detail header). */
  size?: "sm" | "md" | "lg"
  className?: string
}

// Full, literal class names — NOT built via template-literal
// interpolation. Tailwind's JIT content scanner only keeps hand-authored
// `@layer utilities` rules whose selector class appears as a complete,
// literal token somewhere in the scanned source; a `` `course-cover-tint-${n}` ``
// interpolation never produces that literal, so the matching CSS rules
// get silently purged from the build. Spelling out the array keeps every
// variant's full class name visible to the scanner.
const TINT_CLASSES = [
  "course-cover-tint-1",
  "course-cover-tint-2",
  "course-cover-tint-3",
  "course-cover-tint-4",
  "course-cover-tint-5",
] as const

// Small, fast, deterministic string hash (djb2-ish) — good enough to
// spread course ids evenly across the five chart tints without pulling
// in a hashing library for a purely cosmetic pick.
function hashToIndex(input: string, modulo: number): number {
  let hash = 5381
  for (let i = 0; i < input.length; i++) {
    hash = (hash * 33) ^ input.charCodeAt(i)
  }
  return Math.abs(hash) % modulo
}

const LETTER_SIZE: Record<NonNullable<CourseCoverFallbackProps["size"]>, string> = {
  sm: "text-xl",
  md: "text-6xl",
  lg: "text-8xl",
}

/**
 * Deterministic auto-generated cover art for courses without an
 * uploaded image — a tinted diagonal wash (picked from the existing
 * ``--chart-{1..5}`` categorical palette) plus the course's initial
 * letter, so the catalog and dashboards show varied, editorial-looking
 * cards instead of a repeated flat gray rectangle + generic icon.
 *
 * Purely decorative — the course title is always rendered as real text
 * next to/below this, so the monogram is ``aria-hidden``.
 */
export function CourseCoverFallback({ courseId, title, size = "md", className }: CourseCoverFallbackProps) {
  const tintClass = useMemo(
    () => TINT_CLASSES[hashToIndex(courseId, TINT_CLASSES.length)],
    [courseId],
  )
  const letter = useMemo(() => {
    const trimmed = title.trim()
    return trimmed ? trimmed.charAt(0).toUpperCase() : "?"
  }, [title])

  return (
    <div
      className={cn(
        "flex h-full w-full items-center justify-center overflow-hidden",
        tintClass,
        className,
      )}
      aria-hidden="true"
    >
      <span
        className={cn(
          "course-cover-letter select-none font-serif font-semibold leading-none",
          LETTER_SIZE[size],
        )}
      >
        {letter}
      </span>
    </div>
  )
}
