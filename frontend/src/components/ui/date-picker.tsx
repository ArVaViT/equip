import { useTranslation } from "react-i18next"
import { CalendarPopover } from "@/components/ui/CalendarPopover"
import { parseYmd, startOfMonth, ymdKey } from "@/lib/calendar"
import { cn } from "@/lib/utils"

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

function formatLong(ymd: string, locale: string): string {
  const d = parseYmd(ymd)
  if (!d) return ymd
  return d.toLocaleDateString(locale, { day: "numeric", month: "long", year: "numeric" })
}

/**
 * Single-date picker built on the shared {@link CalendarPopover} (Mon-start
 * month grid). Replaces native ``<input type="date">`` whose look diverges
 * across Win/Mac/Linux and which read as a debug control inside an otherwise
 * editorial layout.
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

  return (
    <CalendarPopover
      id={id}
      aria-label={ariaLabel}
      active={active}
      disabled={disabled}
      className={className}
      triggerLabel={value ? formatLong(value, i18n.language) : placeholder ?? t("datePicker.placeholder")}
      triggerMuted={!value}
      initialMonth={startOfMonth(parseYmd(value) ?? new Date())}
      renderDay={(date, { isToday }) => {
        const selected = !!value && ymdKey(date) === value
        return {
          selected,
          className: cn(
            isToday && !selected && "ring-1 ring-primary/60",
            selected && "bg-brand font-medium text-brand-foreground hover:bg-brand/90",
          ),
        }
      }}
      onPickDay={(date, close) => {
        onChange(ymdKey(date))
        close()
      }}
      onClear={() => onChange("")}
      clearDisabled={!value}
    />
  )
}
