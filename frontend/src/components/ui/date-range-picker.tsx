import { useTranslation } from "react-i18next"
import { CalendarPopover } from "@/components/ui/CalendarPopover"
import { parseYmd, startOfMonth, ymdKey } from "@/lib/calendar"
import { cn } from "@/lib/utils"

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

function compareYmd(a: string, b: string): number {
  // ISO YYYY-MM-DD strings compare lexicographically.
  return a < b ? -1 : a > b ? 1 : 0
}

function formatShort(ymd: string, locale: string): string {
  const d = parseYmd(ymd)
  if (!d) return ymd
  return d.toLocaleDateString(locale, { day: "numeric", month: "short", year: "numeric" })
}

/**
 * Single-trigger range picker on the shared {@link CalendarPopover}. Click
 * once to set the lower bound, click again to set the upper bound. The bounds
 * normalise on render so clicking earlier then later — or later then earlier —
 * both produce a valid range; callers receive ``{from, to}`` already sorted.
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

  const triggerLabel = (() => {
    if (value.from && value.to) {
      return `${formatShort(value.from, i18n.language)} – ${formatShort(value.to, i18n.language)}`
    }
    if (value.from) return `${formatShort(value.from, i18n.language)} – …`
    if (value.to) return `… – ${formatShort(value.to, i18n.language)}`
    return placeholder ?? t("dateRangePicker.placeholder")
  })()

  // Normalise so ``lo`` is the lower bound regardless of click order.
  const [lo, hi] =
    value.from && value.to && compareYmd(value.from, value.to) > 0
      ? [value.to, value.from]
      : [value.from, value.to]

  function pick(d: Date, close: () => void) {
    const key = ymdKey(d)
    // First click (no bounds yet) → set the lower bound.
    // Second click (one bound) → set the other bound and close.
    // Both bounds set → start a fresh range from this click.
    if (!value.from && !value.to) {
      onChange({ from: key, to: "" })
      return
    }
    if (value.from && !value.to) {
      onChange({ from: value.from, to: key })
      close()
      return
    }
    if (!value.from && value.to) {
      onChange({ from: key, to: value.to })
      close()
      return
    }
    onChange({ from: key, to: "" })
  }

  return (
    <CalendarPopover
      active={active}
      disabled={disabled}
      className={className}
      triggerLabel={triggerLabel}
      triggerMuted={!value.from && !value.to}
      initialMonth={startOfMonth(parseYmd(value.from) ?? new Date())}
      renderDay={(date, { isToday }) => {
        const key = ymdKey(date)
        const isStart = !!lo && key === lo
        const isEnd = !!hi && hi !== lo && key === hi
        const inRange = !!lo && !!hi && key >= lo && key <= hi
        return {
          selected: isStart || isEnd,
          className: cn(
            isToday && !isStart && !isEnd && "ring-1 ring-primary/60",
            inRange && !isStart && !isEnd && "bg-brand/15 text-ink",
            (isStart || isEnd) && "bg-brand font-medium text-brand-foreground hover:bg-brand/90",
          ),
        }
      }}
      onPickDay={pick}
      onClear={() => onChange({ from: "", to: "" })}
      clearDisabled={!value.from && !value.to}
    />
  )
}
