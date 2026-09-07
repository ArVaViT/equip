import { useMemo, useState, type ReactNode } from "react"
import { useTranslation } from "react-i18next"
import { Calendar as CalendarIcon, ChevronLeft, ChevronRight, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { Eyebrow } from "@/components/patterns"
import { addMonths, buildMonthMatrix, ymdKey } from "@/lib/calendar"
import { cn } from "@/lib/utils"

/** Per-day presentation the host picker computes from its own selection. */
export interface DayRender {
  /** Extra classes layered onto the shared day-cell base. */
  className?: string
  /** Drives `aria-pressed` on the day button. */
  selected?: boolean
}

interface CalendarPopoverProps {
  /** Text shown inside the trigger button. */
  triggerLabel: string
  /** Mute the trigger text (i.e. showing a placeholder, not a value). */
  triggerMuted: boolean
  /** Month the grid opens on (the host derives this from its value). */
  initialMonth: Date
  /** Selection styling for one day cell. */
  renderDay: (date: Date, ctx: { inCurrentMonth: boolean; isToday: boolean }) => DayRender
  /** A day was clicked; `close()` dismisses the popover (host decides when). */
  onPickDay: (date: Date, close: () => void) => void
  /** Clears the value. */
  onClear: () => void
  clearDisabled: boolean
  /** Optional content between the grid and the Clear footer (e.g. a time row). */
  belowGrid?: ReactNode
  disabled?: boolean
  active?: boolean
  className?: string
  id?: string
  "aria-label"?: string
}

/**
 * The shared chrome for the date-input pickers: a Popover whose trigger is
 * an editorial outline button, opening a Mon-start month grid with prev/next
 * month nav and a Clear footer. Selection semantics (single date, datetime,
 * range) live in the host via `renderDay` + `onPickDay`; everything visual is
 * here so the three pickers can't drift apart again.
 */
export function CalendarPopover({
  triggerLabel,
  triggerMuted,
  initialMonth,
  renderDay,
  onPickDay,
  onClear,
  clearDisabled,
  belowGrid,
  disabled,
  active,
  className,
  id,
  "aria-label": ariaLabel,
}: CalendarPopoverProps) {
  const { t, i18n } = useTranslation()
  const [open, setOpen] = useState(false)
  const [anchor, setAnchor] = useState<Date>(initialMonth)

  const days = useMemo(() => buildMonthMatrix(anchor), [anchor])
  const todayKey = ymdKey(new Date())
  const anchorMonth = anchor.getMonth()

  const weekdayHeads = [
    t("streak.days.mon"),
    t("streak.days.tue"),
    t("streak.days.wed"),
    t("streak.days.thu"),
    t("streak.days.fri"),
    t("streak.days.sat"),
    t("streak.days.sun"),
  ]

  const monthLabel = anchor.toLocaleDateString(i18n.language, {
    month: "long",
    year: "numeric",
  })

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          id={id}
          type="button"
          variant="outline"
          size="sm"
          disabled={disabled}
          aria-label={ariaLabel}
          className={cn(
            "h-9 justify-start gap-2 px-3 font-normal",
            triggerMuted && "text-ink-muted",
            active && "border-brand/40 ring-1 ring-primary/40",
            className,
          )}
        >
          <CalendarIcon className="h-3.5 w-3.5 shrink-0" strokeWidth={1.75} aria-hidden />
          <span className="truncate text-xs sm:text-sm">{triggerLabel}</span>
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-[min(20rem,calc(100vw-2rem))] max-w-sm p-0" align="start">
        <div className="flex items-center justify-between gap-2 border-b border-edge px-3 py-2">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="h-7 w-7 p-0"
            onClick={() => setAnchor((a) => addMonths(a, -1))}
            aria-label={t("dateRangePicker.prevMonth")}
          >
            <ChevronLeft className="h-4 w-4" strokeWidth={1.75} aria-hidden />
          </Button>
          {/* `capitalize` here read "Август 2026 Г." — CSS capitalizes every word,
              and Russian writes months and the "г." abbreviation in lower case.
              Only the first letter of the label is ours to raise. */}
          <p className="text-sm font-medium text-ink first-letter:uppercase">{monthLabel}</p>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="h-7 w-7 p-0"
            onClick={() => setAnchor((a) => addMonths(a, 1))}
            aria-label={t("dateRangePicker.nextMonth")}
          >
            <ChevronRight className="h-4 w-4" strokeWidth={1.75} aria-hidden />
          </Button>
        </div>

        <div className="p-2">
          <div className="grid grid-cols-7 gap-0.5">
            {weekdayHeads.map((d, i) => (
              <Eyebrow as="div" key={i} className="pb-1 text-center">
                {d}
              </Eyebrow>
            ))}
            {days.map((date, i) => {
              const inCurrentMonth = date.getMonth() === anchorMonth
              const isToday = ymdKey(date) === todayKey
              const { className: dayClass, selected } = renderDay(date, {
                inCurrentMonth,
                isToday,
              })
              return (
                <button
                  type="button"
                  key={i}
                  onClick={() => onPickDay(date, () => setOpen(false))}
                  className={cn(
                    "relative flex h-8 w-full items-center justify-center rounded-sm text-xs tabular-nums",
                    "transition-colors hover:bg-muted",
                    inCurrentMonth ? "text-ink" : "text-ink-muted",
                    dayClass,
                  )}
                  aria-label={date.toLocaleDateString(i18n.language, {
                    weekday: "long",
                    day: "numeric",
                    month: "long",
                    year: "numeric",
                  })}
                  aria-pressed={!!selected}
                >
                  {date.getDate()}
                </button>
              )
            })}
          </div>
        </div>

        {belowGrid}

        <div className="flex items-center justify-end gap-2 border-t border-edge px-2 py-1.5">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={onClear}
            disabled={clearDisabled}
            className="h-7 text-xs text-ink-muted hover:text-ink"
          >
            <X className="mr-1 h-3 w-3" strokeWidth={1.75} aria-hidden />
            {t("dateRangePicker.clear")}
          </Button>
        </div>
      </PopoverContent>
    </Popover>
  )
}
