import { useMemo, useState } from "react"
import { useTranslation } from "react-i18next"
import { Calendar as CalendarIcon, ChevronLeft, ChevronRight, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { cn } from "@/lib/utils"

const DAYS_IN_WEEK = 7

export interface DateRange {
  /** YYYY-MM-DD string. ``""`` means "no lower bound". */
  from: string
  /** YYYY-MM-DD string. ``""`` means "no upper bound". */
  to: string
}

interface Props {
  value: DateRange
  onChange: (next: DateRange) => void
  /** Label for the field; rendered above the trigger by callers. */
  label?: string
  /** Placeholder shown inside the trigger when neither bound is set. */
  placeholder?: string
  /** Disable the trigger. */
  disabled?: boolean
  /** Visually mark the trigger as "this filter is active" — same ring
   *  treatment the surrounding admin filters use. */
  active?: boolean
  className?: string
}

function ymdKey(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`
}

function parseYmd(s: string): Date | null {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(s)) return null
  const y = Number(s.slice(0, 4))
  const m = Number(s.slice(5, 7))
  const d = Number(s.slice(8, 10))
  const out = new Date(y, m - 1, d)
  return Number.isNaN(out.getTime()) ? null : out
}

function weekdayMonStart(d: Date): number {
  return (d.getDay() + 6) % DAYS_IN_WEEK
}

function startOfMonth(d: Date): Date {
  return new Date(d.getFullYear(), d.getMonth(), 1)
}

function addMonths(d: Date, n: number): Date {
  return new Date(d.getFullYear(), d.getMonth() + n, 1)
}

function compareYmd(a: string, b: string): number {
  // ISO YYYY-MM-DD strings compare lexicographically.
  return a < b ? -1 : a > b ? 1 : 0
}

interface MonthCell {
  date: Date
  inCurrentMonth: boolean
  isToday: boolean
  isStart: boolean
  isEnd: boolean
  inRange: boolean
}

function buildMonthGrid(anchor: Date, from: string, to: string): MonthCell[] {
  const year = anchor.getFullYear()
  const month = anchor.getMonth()
  const first = new Date(year, month, 1)
  const offset = weekdayMonStart(first)
  const gridStart = new Date(year, month, 1 - offset)
  const todayKey = ymdKey(new Date())

  // Normalise so ``from`` is the lower bound regardless of click order
  // (lets the second click be either earlier or later than the first).
  const [lo, hi] = from && to && compareYmd(from, to) > 0 ? [to, from] : [from, to]

  const cells: MonthCell[] = []
  for (let i = 0; i < 42; i++) {
    const d = new Date(gridStart.getFullYear(), gridStart.getMonth(), gridStart.getDate() + i)
    const key = ymdKey(d)
    const isStart = !!lo && key === lo
    const isEnd = !!hi && hi !== lo && key === hi
    const inRange = !!lo && !!hi && key >= lo && key <= hi
    cells.push({
      date: d,
      inCurrentMonth: d.getMonth() === month,
      isToday: key === todayKey,
      isStart,
      isEnd,
      inRange,
    })
  }
  return cells
}

/**
 * Single-trigger range picker. Click once to set the lower bound,
 * click again to set the upper bound. The bounds normalise on render
 * so clicking earlier then later — or later then earlier — both
 * produce a valid range; callers receive ``{from, to}`` already
 * sorted.
 *
 * Native ``<input type=date>`` was the previous filter pattern in
 * the admin audit log; it renders differently in every browser, has
 * no range semantics, and reads as a debug control rather than part
 * of the system. This widget uses the same Mon-start week + 6-row
 * month grid the dashboard already uses, so the visual vocabulary
 * stays consistent across the app.
 */
export function DateRangePicker({
  value,
  onChange,
  placeholder,
  disabled,
  active,
  className,
}: Props) {
  const { t, i18n } = useTranslation()
  const [open, setOpen] = useState(false)
  // The visible month: defaults to the month of ``from`` (so the
  // calendar opens already showing the range), then falls back to
  // today. Stored in state so the chevron nav doesn't clobber the
  // selection.
  const [anchor, setAnchor] = useState<Date>(() => {
    const fromDate = parseYmd(value.from)
    return startOfMonth(fromDate ?? new Date())
  })

  const cells = useMemo(
    () => buildMonthGrid(anchor, value.from, value.to),
    [anchor, value.from, value.to],
  )

  const weekdayHeads = [
    t("streak.days.mon"),
    t("streak.days.tue"),
    t("streak.days.wed"),
    t("streak.days.thu"),
    t("streak.days.fri"),
    t("streak.days.sat"),
    t("streak.days.sun"),
  ]

  const triggerLabel = (() => {
    if (value.from && value.to) {
      return `${formatShort(value.from, i18n.language)} – ${formatShort(value.to, i18n.language)}`
    }
    if (value.from) return `${formatShort(value.from, i18n.language)} – …`
    if (value.to) return `… – ${formatShort(value.to, i18n.language)}`
    return placeholder ?? t("dateRangePicker.placeholder")
  })()

  const monthLabel = anchor.toLocaleDateString(i18n.language, {
    month: "long",
    year: "numeric",
  })

  function pick(d: Date) {
    const key = ymdKey(d)
    // First click (no bounds yet) → set the lower bound.
    // Second click (one bound) → set the other bound.
    // Both bounds set → start a fresh range from this click.
    if (!value.from && !value.to) {
      onChange({ from: key, to: "" })
      return
    }
    if (value.from && !value.to) {
      // Order doesn't matter — normalise on render
      onChange({ from: value.from, to: key })
      // Close after a complete range so the admin can see the table
      // refresh; the trigger label reflects the picked range.
      setOpen(false)
      return
    }
    if (!value.from && value.to) {
      onChange({ from: key, to: value.to })
      setOpen(false)
      return
    }
    // Both bounds present — restart.
    onChange({ from: key, to: "" })
  }

  function clear() {
    onChange({ from: "", to: "" })
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={disabled}
          className={cn(
            "h-9 justify-start gap-2 px-3 font-normal",
            !value.from && !value.to && "text-muted-foreground",
            active && "border-primary/40 ring-1 ring-primary/40",
            className,
          )}
        >
          <CalendarIcon className="h-3.5 w-3.5 shrink-0" strokeWidth={1.75} aria-hidden />
          <span className="truncate text-xs sm:text-sm">{triggerLabel}</span>
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-[300px] p-0" align="start">
        {/* Header: prev / month label / next */}
        <div className="flex items-center justify-between gap-2 border-b border-border px-3 py-2">
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
          <p className="text-sm font-medium capitalize text-foreground">{monthLabel}</p>
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

        {/* Weekday heads + grid */}
        <div className="p-2">
          <div className="grid grid-cols-7 gap-0.5">
            {weekdayHeads.map((d, i) => (
              <div
                key={i}
                className="pb-1 text-center text-[10px] font-medium uppercase tracking-[0.18em] text-muted-foreground"
              >
                {d}
              </div>
            ))}
            {cells.map((c, i) => {
              const buttonClasses = cn(
                "relative flex h-8 w-full items-center justify-center rounded-sm text-xs tabular-nums",
                "transition-colors hover:bg-muted",
                c.inCurrentMonth ? "text-foreground" : "text-muted-foreground/40",
                c.isToday && !c.isStart && !c.isEnd && "ring-1 ring-primary/60",
                c.inRange && !c.isStart && !c.isEnd && "bg-primary/15 text-foreground",
                (c.isStart || c.isEnd) && "bg-primary font-medium text-primary-foreground hover:bg-primary/90",
              )
              return (
                <button
                  type="button"
                  key={i}
                  onClick={() => pick(c.date)}
                  className={buttonClasses}
                  aria-label={c.date.toLocaleDateString(i18n.language, {
                    weekday: "long",
                    day: "numeric",
                    month: "long",
                    year: "numeric",
                  })}
                  aria-pressed={c.isStart || c.isEnd}
                >
                  {c.date.getDate()}
                </button>
              )
            })}
          </div>
        </div>

        {/* Footer: Clear */}
        <div className="flex items-center justify-end gap-2 border-t border-border px-2 py-1.5">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={clear}
            disabled={!value.from && !value.to}
            className="h-7 text-xs text-muted-foreground hover:text-foreground"
          >
            <X className="mr-1 h-3 w-3" strokeWidth={1.75} aria-hidden />
            {t("dateRangePicker.clear")}
          </Button>
        </div>
      </PopoverContent>
    </Popover>
  )
}

function formatShort(ymd: string, locale: string): string {
  const d = parseYmd(ymd)
  if (!d) return ymd
  return d.toLocaleDateString(locale, { day: "numeric", month: "short", year: "numeric" })
}
