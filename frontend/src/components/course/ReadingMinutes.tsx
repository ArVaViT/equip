import { useTranslation } from "react-i18next"

/**
 * "12 min" at the end of an outline row: whether a lesson fits a lunch break.
 * Nothing for a lesson with no reading (a test, an assignment) or before the
 * numbers arrive.
 */
export function ReadingMinutes({ minutes }: { minutes: number | undefined }) {
  const { t } = useTranslation()
  if (!minutes || minutes <= 0) return null
  return (
    <span className="shrink-0 whitespace-nowrap text-xs font-normal text-ink-muted">
      {t("courseDetail.minutesShort", { minutes })}
    </span>
  )
}
