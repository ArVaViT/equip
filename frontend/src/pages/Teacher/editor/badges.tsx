import { useTranslation } from "react-i18next"
import { Badge } from "@/components/ui/badge"
import { EVENT_TYPE_LABEL_KEYS, type EventType } from "./eventTypes"

/** Enrollment-window state derived from (start, end) strings. */
export function EnrollmentStatusBadge({ start, end }: { start: string; end: string }) {
  const { t } = useTranslation()
  if (!start && !end) return <Badge variant="muted">{t("teacherEditor.badges.notSet")}</Badge>
  const now = new Date()
  const s = start ? new Date(start) : null
  const e = end ? new Date(end) : null
  if (s && now < s) return <Badge variant="info">{t("teacherEditor.badges.upcoming")}</Badge>
  if (e && now > e) return <Badge variant="destructive">{t("teacherEditor.badges.closed")}</Badge>
  return <Badge variant="success">{t("teacherEditor.badges.open")}</Badge>
}

type EventVariant =
  | "destructiveSubtle"
  | "infoSubtle"
  | "warningSubtle"
  | "muted"

const EVENT_BADGE_VARIANT: Record<string, EventVariant> = {
  deadline: "destructiveSubtle",
  live_session: "infoSubtle",
  exam: "warningSubtle",
  other: "muted",
}

export function EventTypeBadge({ type }: { type: string }) {
  const { t } = useTranslation()
  // Fall back to "other" for unknown types so we still render a sensible
  // localized label (the i18n keys cover the four supported types).
  const key: EventType = (type in EVENT_TYPE_LABEL_KEYS ? type : "other") as EventType
  return (
    <Badge variant={EVENT_BADGE_VARIANT[type] ?? "muted"}>
      {t(EVENT_TYPE_LABEL_KEYS[key])}
    </Badge>
  )
}

// CohortStatusBadge was used only by the (now-removed) teacher CohortsModal.
// When the admin cohort UI ships (issue #212) it will own the cohort badge
// in `pages/Admin/cohorts/`.
