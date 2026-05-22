import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { ChevronDown, ChevronUp, Megaphone, Trash2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import { formatDateTime } from "@/i18n/format"
import type { Announcement } from "@/types"

interface AnnouncementPagerProps {
  announcements: Announcement[]
  /** Required only on surfaces where the viewer may delete entries
   *  (i.e. the teacher's editor modal). Omitted on read-only feeds
   *  (course detail page, banner, public surfaces). */
  onDelete?: (id: string) => void
}

// At more than this many entries the dot column reads as clutter; we
// swap to a compact "current / total" counter instead so the rail
// stays the same height regardless of how many posts the teacher has.
const DOTS_CAP = 7

/**
 * Step-through view over a list of announcements. The host (teacher
 * modal or student course page) stays one card tall regardless of
 * how many posts exist.
 *
 * Layout: the announcement body fills the card; a slim vertical rail
 * on the right of the card holds the navigation (↑ at top, ↓ at
 * bottom, dot indicators or a counter between them). The rail spans
 * the full card height so the affordance is always visible without
 * scrolling. The trash button (when allowed) lives in the content
 * area's top-right corner, separate from the nav rail.
 *
 * Owns only the cursor index; the list, ordering, and the delete
 * action all belong to the parent. The cursor clamps after deletes
 * (so the card never blanks) and is *not* moved when a fresh
 * announcement is posted — the reader keeps reading what they were
 * on instead of getting yanked to the new entry.
 *
 * Keyboard: ↑ / ↓ step when focus is inside the pager. ← / → also
 * step (kept for parity with the previous horizontal layout). The
 * listener is element-scoped, never window-level, so the keys never
 * fight surrounding form inputs.
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
    if (e.key === "ArrowUp" || e.key === "ArrowLeft") {
      e.preventDefault()
      step(-1)
    } else if (e.key === "ArrowDown" || e.key === "ArrowRight") {
      e.preventDefault()
      step(1)
    }
  }

  const hasNav = total > 1
  const showDots = hasNav && total <= DOTS_CAP

  return (
    <div
      role="region"
      aria-roledescription={t("teacherEditor.modals.announcements.carouselRole")}
      aria-label={t("teacherEditor.modals.announcements.title")}
      onKeyDown={onKeyDown}
      tabIndex={-1}
      className="flex overflow-hidden rounded-lg border bg-card"
    >
      <div className="flex min-w-0 flex-1 items-start gap-3 p-3 sm:p-4">
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
      {hasNav && (
        <div className="flex shrink-0 flex-col items-center justify-between gap-2 border-l bg-muted/40 px-1.5 py-2">
          <Button
            variant="ghost"
            size="sm"
            className="h-7 w-7 p-0"
            onClick={() => step(-1)}
            disabled={index === 0}
            aria-label={t("teacherEditor.modals.announcements.prevAria")}
          >
            <ChevronUp className="h-4 w-4" strokeWidth={1.75} aria-hidden />
          </Button>
          {showDots ? (
            <div className="flex flex-col items-center gap-1.5" aria-hidden>
              {announcements.map((a, i) => (
                <span
                  key={a.id}
                  className={cn(
                    "h-1.5 w-1.5 rounded-full transition-colors duration-150",
                    i === index ? "bg-primary" : "bg-muted-foreground/30",
                  )}
                />
              ))}
            </div>
          ) : (
            <span
              className="text-[10px] leading-none tabular-nums text-muted-foreground"
              aria-hidden
            >
              {t("teacherEditor.modals.announcements.position", {
                current: index + 1,
                total,
              })}
            </span>
          )}
          <Button
            variant="ghost"
            size="sm"
            className="h-7 w-7 p-0"
            onClick={() => step(1)}
            disabled={index === total - 1}
            aria-label={t("teacherEditor.modals.announcements.nextAria")}
          >
            <ChevronDown className="h-4 w-4" strokeWidth={1.75} aria-hidden />
          </Button>
        </div>
      )}
    </div>
  )
}
