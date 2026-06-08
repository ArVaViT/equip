import { useTranslation } from "react-i18next"
import { Input } from "@/components/ui/input"
import { CalendarPopover } from "@/components/ui/CalendarPopover"
import { startOfMonth, ymdKey } from "@/lib/calendar"
import { cn } from "@/lib/utils"

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

function parseLocal(s: string): { date: Date; hh: number; mm: number } | null {
  // Tolerant parser for ``YYYY-MM-DDTHH:MM`` and ``YYYY-MM-DDTHH:MM:SS``.
  const m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/.exec(s)
  if (!m) return null
  const date = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]))
  if (Number.isNaN(date.getTime())) return null
  return { date, hh: Number(m[4]), mm: Number(m[5]) }
}

function compose(date: Date, hh: number, mm: number): string {
  const hhs = String(hh).padStart(2, "0")
  const mms = String(mm).padStart(2, "0")
  return `${ymdKey(date)}T${hhs}:${mms}`
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

const clampHH = (n: number) => Math.min(23, Math.max(0, Number.isFinite(n) ? Math.round(n) : 0))
const clampMM = (n: number) => Math.min(59, Math.max(0, Number.isFinite(n) ? Math.round(n) : 0))

/**
 * Date + time picker built on the shared {@link CalendarPopover} with a time
 * row below the grid. Replaces native ``<input type="datetime-local">`` whose
 * look diverges across Win/Mac/Linux (and which, on Windows, opens a chunky
 * non-keyboard-navigable popup that visually breaks the editorial layout).
 *
 * Value contract is identical to the native input: ``"YYYY-MM-DDTHH:MM"`` ⇄
 * ``""``. Time inputs use plain ``<Input type="number">`` so we don't pay for
 * a second native picker.
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

  const parsed = parseLocal(value)
  const selectedYmd = parsed ? ymdKey(parsed.date) : ""
  const hh = parsed?.hh ?? 9
  const mm = parsed?.mm ?? 0

  const setHH = (next: number) => onChange(compose(parsed?.date ?? new Date(), next, mm))
  const setMM = (next: number) => onChange(compose(parsed?.date ?? new Date(), hh, next))

  return (
    <CalendarPopover
      id={id}
      aria-label={ariaLabel}
      active={active}
      disabled={disabled}
      className={className}
      triggerLabel={value ? formatLong(value, i18n.language) : placeholder ?? t("dateTimePicker.placeholder")}
      triggerMuted={!value}
      initialMonth={startOfMonth(parsed?.date ?? new Date())}
      renderDay={(date, { isToday }) => {
        const selected = !!selectedYmd && ymdKey(date) === selectedYmd
        return {
          selected,
          className: cn(
            isToday && !selected && "ring-1 ring-primary/60",
            selected && "bg-brand font-medium text-brand-foreground hover:bg-brand/90",
          ),
        }
      }}
      onPickDay={(date) => onChange(compose(date, hh, mm))}
      onClear={() => onChange("")}
      clearDisabled={!value}
      belowGrid={
        <div className="flex items-center justify-center gap-1.5 border-t border-edge px-3 py-2 text-xs">
          <Input
            type="number"
            min={0}
            max={23}
            value={String(hh).padStart(2, "0")}
            onChange={(e) => setHH(clampHH(Number(e.target.value)))}
            className="h-7 w-12 px-1 text-center tabular-nums"
            aria-label={t("dateTimePicker.hourAria")}
          />
          <span className="font-medium text-ink-muted">:</span>
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
      }
    />
  )
}
