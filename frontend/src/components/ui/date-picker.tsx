import { useMemo, useState } from "react"
import { useTranslation } from "react-i18next"
import { Calendar as CalendarIcon, ChevronLeft, ChevronRight, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { cn } from "@/lib/utils"

const DAYS_IN_WEEK = 7

interface Props {
  /** YYYY-MM-DD string. ``""`` means "no value". */
  value: string
  onChange: (next: string) => void
  placeholder?: string
  disabled?: boolean
  /** Style the trigger as "this field is active" — same ring as the
   *  surrounding admin filter selects. */
  active?: boolean
  className?: string
  /** Forwarded to the trigger so an external ``<label htmlFor>`` works. */
  id?: string
  /** Forwarded to the trigger when no visible label is rendered. */
  "aria-label"?: string
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

interface MonthCell {
  date: Date
  inCurrentMonth: boolean
  isToday: boolean
  isSelected: boolean
}

function buildMonthGrid(anchor: Date, selected: string): MonthCell[] {
  const year = anchor.getFullYear()
  const month = anchor.getMonth()
  const first = new Date(year, month, 1)
  const offset = weekdayMonStart(first)
  const gridStart = new Date(year, month, 1 - offset)
  const todayKey = ymdKey(new Date())

  const cells: MonthCell[] = []
  for (let i = 0; i < 42; i++) {
    const d = new Date(gridStart.getFullYear(), gridStart.getMonth(), gridStart.getDate() + i)
    const key = ymdKey(d)
    cells.push({
      date: d,
      inCurrentMonth: d.getMonth() === month,
      isToday: key === todayKey,
      isSelected: !!selected && key === selected,
    })
  }
  return cells
}

function formatLong(ymd: string, locale: string): string {
  const d = parseYmd(ymd)
  if (!d) return ymd
  return d.toLocaleDateString(locale, { day: "numeric", month: "long", year: "numeric" })
}

/**
 * Single-date picker built on the same hand-rolled Popover + Mon-start
 * month-grid pattern as ``DateRangePicker``. Replaces native
 * ``<input type="date">`` whose look diverges across Win/Mac/Linux and
 * which read as a debug control inside an otherwise editorial layout.
 *
 * Value contract is unchanged from the native input: ``"YYYY-MM-DD"`` ⇄
 * ``""``. Drop-in replacement for any caller that read ``e.target.value``.
 */
export function DatePicker({
  value,
  onChange,
  placeholder,
  disabled,
  active,
  className,
  id,
  "aria-label": ariaLabel,
}: Props) {
  const { t, i18n } = useTranslation()
  const [open, setOpen] = useState(false)
  const [anchor, setAnchor] = useState<Date>(() => {
    const v = parseYmd(value)
    return startOfMonth(v ?? new Date())
  })

  const cells = useMemo(() => buildMonthGrid(anchor, value), [anchor, value])

  const weekdayHeads = [
    t("streak.days.mon"),
    t("streak.days.tue"),
    t("streak.days.wed"),
    t("streak.days.thu"),
    t("streak.days.fri"),
    t("streak.days.sat"),
    t("streak.days.sun"),
  ]

  const triggerLabel = value
    ? formatLong(value, i18n.language)
    : placeholder ?? t("datePicker.placeholder")

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
            !value && "text-muted-foreground",
            active && "border-primary/40 ring-1 ring-primary/40",
            className,
          )}
        >
          <CalendarIcon className="h-3.5 w-3.5 shrink-0" strokeWidth={1.75} aria-hidden />
          <span className="truncate text-xs sm:text-sm">{triggerLabel}</span>
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-[300px] p-0" align="start">
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
            {cells.map((c, i) => (
              <button
                type="button"
                key={i}
                onClick={() => {
                  onChange(ymdKey(c.date))
                  setOpen(false)
                }}
                className={cn(
                  "relative flex h-8 w-full items-center justify-center rounded-sm text-xs tabular-nums",
                  "transition-colors hover:bg-muted",
                  c.inCurrentMonth ? "text-foreground" : "text-muted-foreground/40",
                  c.isToday && !c.isSelected && "ring-1 ring-primary/60",
                  c.isSelected && "bg-primary font-medium text-primary-foreground hover:bg-primary/90",
                )}
                aria-label={c.date.toLocaleDateString(i18n.language, {
                  weekday: "long",
                  day: "numeric",
                  month: "long",
                  year: "numeric",
                })}
                aria-pressed={c.isSelected}
              >
                {c.date.getDate()}
              </button>
            ))}
          </div>
        </div>

        <div className="flex items-center justify-end gap-2 border-t border-border px-2 py-1.5">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => onChange("")}
            disabled={!value}
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
