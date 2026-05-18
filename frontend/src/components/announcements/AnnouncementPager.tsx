import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { ChevronLeft, ChevronRight, Megaphone, Trash2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { formatDateTime } from "@/i18n/format"
import type { Announcement } from "@/types"

interface AnnouncementPagerProps {
  announcements: Announcement[]
  /** Required only on surfaces where the viewer may delete entries
   *  (i.e. the teacher's editor modal). Omitted on read-only feeds
   *  (course detail page, banner, public surfaces). */
  onDelete?: (id: string) => void
}

/**
 * Step-through view over a list of announcements. Replaces the vertical
 * stack so the host (teacher modal or student course page) stays one
 * card tall regardless of how many posts exist, with prev/next arrows
 * and a position counter.
 *
 * Owns only the cursor index; the list, ordering, and the delete
 * action all belong to the parent. The cursor clamps after deletes
 * (so the card never blanks) and is *not* moved when a fresh
 * announcement is posted — the reader keeps reading what they were
 * on instead of getting yanked to the new entry.
 *
 * Keyboard: ← / → step when focus is anywhere inside the pager. We do
 * NOT install a window-level listener, so the keys never fight any
 * surrounding form inputs (e.g. the post-form sitting next to the
 * pager in the teacher modal).
 */
export function AnnouncementPager({ announcements, onDelete }: AnnouncementPagerProps) {
  const { t } = useTranslation()
  const [index, setIndex] = useState(0)
  const total = announcements.length

  // Clamp on shrink (after a delete drops the tail). One render with the
  // ``!current`` early-return below covers the in-between tick.
  useEffect(() => {
    if (total > 0 && index > total - 1) setIndex(total - 1)
  }, [index, total])

  if (total === 0) return null
  const current = announcements[index]
  if (!current) return null

  const step = (delta: number) => {
    setIndex((i) => Math.min(Math.max(0, i + delta), total - 1))
  }

  const onKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    if (e.key === "ArrowLeft") {
      e.preventDefault()
      step(-1)
    } else if (e.key === "ArrowRight") {
      e.preventDefault()
      step(1)
    }
  }

  return (
    <div
      role="region"
      aria-roledescription={t("teacherEditor.modals.announcements.carouselRole")}
      aria-label={t("teacherEditor.modals.announcements.title")}
      onKeyDown={onKeyDown}
      tabIndex={-1}
      className="rounded-lg border bg-card"
    >
      <div className="flex items-start gap-3 p-3 sm:p-4">
        <Megaphone className="mt-0.5 h-4 w-4 shrink-0 text-info" strokeWidth={1.75} aria-hidden />
        <div className="min-w-0 flex-1">
          {/* Polite live region announces the new title when the
              teacher steps via arrows or buttons. ``aria-atomic`` so
              the whole title is read each time, not just the diff. */}
          <p
            className="text-sm font-medium text-wrap-safe"
            aria-live="polite"
            aria-atomic="true"
          >
            {current.title}
          </p>
          {current.content && (
            <p className="mt-0.5 text-xs text-muted-foreground text-wrap-safe whitespace-pre-line">
              {current.content}
            </p>
          )}
          <time className="mt-1 block text-xs text-muted-foreground/60">
            {formatDateTime(current.created_at)}
          </time>
        </div>
        {onDelete && (
          <Button
            variant="ghost"
            size="sm"
            className="h-7 w-7 shrink-0 p-0 text-destructive hover:text-destructive"
            onClick={() => onDelete(current.id)}
            aria-label={t("teacherEditor.modals.announcements.deleteAria", { title: current.title })}
          >
            <Trash2 className="h-3.5 w-3.5" strokeWidth={1.75} />
          </Button>
        )}
      </div>
      {total > 1 && (
        <div className="flex items-center justify-between border-t bg-muted/40 px-2 py-1.5">
          <Button
            variant="ghost"
            size="sm"
            className="h-7 w-7 p-0"
            onClick={() => step(-1)}
            disabled={index === 0}
            aria-label={t("teacherEditor.modals.announcements.prevAria")}
          >
            <ChevronLeft className="h-4 w-4" strokeWidth={1.75} aria-hidden />
          </Button>
          <span className="text-xs tabular-nums text-muted-foreground" aria-hidden>
            {t("teacherEditor.modals.announcements.position", {
              current: index + 1,
              total,
            })}
          </span>
          <Button
            variant="ghost"
            size="sm"
            className="h-7 w-7 p-0"
            onClick={() => step(1)}
            disabled={index === total - 1}
            aria-label={t("teacherEditor.modals.announcements.nextAria")}
          >
            <ChevronRight className="h-4 w-4" strokeWidth={1.75} aria-hidden />
          </Button>
        </div>
      )}
    </div>
  )
}
