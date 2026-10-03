import { Clock } from "lucide-react"
import { useTranslation } from "react-i18next"

import { activeIntlTag } from "@/i18n/config"
import { cn } from "@/lib/utils"

/**
 * Reading time as the eye expects it: a clock and a number — "12 мин",
 * "≈ 2,5 ч". The whole phrase is for the screen reader only.
 *
 * An hour or more is rounded to the nearest half hour: an estimate that
 * pretends to a tenth of an hour is not more honest, only noisier.
 */
export function ReadingMinutes({
  minutes,
  className,
  iconClassName = "h-3 w-3",
}: {
  minutes: number | undefined
  /** Replaces the default size and colour; layout and no-wrap stay. */
  className?: string
  /** To match the icons beside it in a header line. */
  iconClassName?: string
}) {
  const { t, i18n } = useTranslation()
  if (!minutes || minutes <= 0) return null
  let short: string
  let full: string
  if (minutes < 60) {
    short = t("courseDetail.minutesShort", { minutes })
    full = t("chapter.readingTime", { count: minutes })
  } else {
    const hours = new Intl.NumberFormat(activeIntlTag(i18n.resolvedLanguage ?? i18n.language), {
      maximumFractionDigits: 1,
    }).format(Math.round(minutes / 30) / 2)
    short = t("courseDetail.hoursShort", { hours })
    full = t("courseDetail.readingHours", { hours })
  }
  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center whitespace-nowrap tabular-nums",
        className ?? "gap-1 text-xs font-normal text-ink-muted",
      )}
    >
      <Clock className={iconClassName} strokeWidth={1.75} aria-hidden />
      <span aria-hidden>{short}</span>
      <span className="sr-only">{full}</span>
    </span>
  )
}
