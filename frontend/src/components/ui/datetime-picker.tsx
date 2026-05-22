import { useMemo, useState } from "react"
import { useTranslation } from "react-i18next"
import { Calendar as CalendarIcon, ChevronLeft, ChevronRight, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { cn } from "@/lib/utils"

const DAYS_IN_WEEK = 7

interface Props {
  /** ``"YYYY-MM-DDTHH:MM"`` string — identical contract to the native
   *  ``<input type="datetime-local">`` this widget replaces. ``""`` for
   *  "no value". */
  value: string
  onChange: (next: string) => void
  placeholder?: string
  disabled?: boolean
  active?: boolean
  className?: string
  id?: string
  "aria-label"?: string
}

function ymdKey(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`
}

function parseLocal(s: string): { date: Date; hh: number; mm: number } | null {
  // Tolerant parser for ``YYYY-MM-DDTHH:MM`` and ``YYYY-MM-DDTHH:MM:SS``.
  const m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/.exec(s)
  if (!m) return null
  const date = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]))
  if (Number.isNaN(date.getTime())) return null
  return { date, hh: Number(m[4]), mm: Number(m[5]) }
}

function compose(date: Date, hh: number, mm: number): string {
  const day = ymdKey(date)
  const hhs = String(hh).padStart(2, "0")
  const mms = String(mm).padStart(2, "0")
  return `${day}T${hhs}:${mms}`
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

function buildMonthGrid(anchor: Date, selectedYmd: string): MonthCell[] {
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
      isSelected: !!selectedYmd && key === selectedYmd,
    })
  }
  return cells
}

function formatLong(value: string, locale: string): string {
  const parsed = parseLocal(value)
  if (!parsed) return value
  const datePart = parsed.date.toLocaleDateString(locale, {
    day: "numeric",
    month: "short",
    year: "numeric",
  })
  const hh = String(parsed.hh).padStart(2, "0")
  const mm = String(parsed.mm).padStart(2, "0")
  return `${datePart} · ${hh}:${mm}`
}

/**
 * Date + time picker built on the same hand-rolled Popover + Mon-start
 * month-grid pattern as ``DateRangePicker``. Replaces native
 * ``<input type="datetime-local">`` whose look diverges across
 * Win/Mac/Linux (and which, on Windows, opens a chunky non-keyboard-
 * navigable popup that visually breaks the editorial layout).
 *
 * Value contract is identical to the native input: ``"YYYY-MM-DDTHH:MM"``
 * ⇄ ``""``. Drop-in replacement for any caller that read
 * ``e.target.value`` from a datetime-local input.
 *
 * Time inputs use plain ``<Input type="number">`` so we don't pay for
 * a second native picker — HH (00-23) and MM (00-59) sit at the bottom
 * of the popover as two small editable cells.
 */
export function DateTimePicker({
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

  const parsed = parseLocal(value)
  const selectedYmd = parsed ? ymdKey(parsed.date) : ""
  const hh = parsed?.hh ?? 9
  const mm = parsed?.mm ?? 0

  const [anchor, setAnchor] = useState<Date>(() =>
    startOfMonth(parsed?.date ?? new Date()),
  )

  const cells = useMemo(
    () => buildMonthGrid(anchor, selectedYmd),
    [anchor, selectedYmd],
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

  const triggerLabel = value
    ? formatLong(value, i18n.language)
    : placeholder ?? t("dateTimePicker.placeholder")

  const monthLabel = anchor.toLocaleDateString(i18n.language, {
    month: "long",
    year: "numeric",
  })

  const setDate = (d: Date) => onChange(compose(d, hh, mm))
  const setHH = (next: number) => {
    if (!parsed) {
      // First time setting time — default to today's date.
      onChange(compose(new Date(), next, mm))
      return
    }
    onChange(compose(parsed.date, next, mm))
  }
  const setMM = (next: number) => {
    if (!parsed) {
      onChange(compose(new Date(), hh, next))
      return
    }
    onChange(compose(parsed.date, hh, next))
  }

  const clampHH = (n: number) => Math.min(23, Math.max(0, Number.isFinite(n) ? Math.round(n) : 0))
  const clampMM = (n: number) => Math.min(59, Math.max(0, Number.isFinite(n) ? Math.round(n) : 0))

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
                onClick={() => setDate(c.date)}
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

        {/* Time row */}
        <div className="flex items-center justify-center gap-1.5 border-t border-border px-3 py-2 text-xs">
          <Input
            type="number"
            min={0}
            max={23}
            value={String(hh).padStart(2, "0")}
            onChange={(e) => setHH(clampHH(Number(e.target.value)))}
            className="h-7 w-12 px-1 text-center tabular-nums"
            aria-label={t("dateTimePicker.hourAria")}
          />
          <span className="font-medium text-muted-foreground">:</span>
          <Input
            type="number"
            min={0}
            max={59}
            value={String(mm).padStart(2, "0")}
            onChange={(e) => setMM(clampMM(Number(e.target.value)))}
            className="h-7 w-12 px-1 text-center tabular-nums"
            aria-label={t("dateTimePicker.minuteAria")}
          />
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
