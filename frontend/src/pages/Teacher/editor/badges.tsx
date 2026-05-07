import { useTranslation } from "react-i18next"
import { Badge } from "@/components/ui/badge"
import type { Cohort } from "@/types"

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

const EVENT_BADGE_CLASS: Record<string, string> = {
  deadline: "bg-destructive/15 text-destructive",
  live_session: "bg-info/15 text-info",
  exam: "bg-warning/15 text-warning",
  other: "bg-muted text-muted-foreground",
}

export function EventTypeBadge({ type }: { type: string }) {
  return (
    <span
      className={`rounded-full px-1.5 py-0.5 text-[10px] font-medium capitalize ${
        EVENT_BADGE_CLASS[type] ?? EVENT_BADGE_CLASS.other
      }`}
    >
      {type.replace("_", " ")}
    </span>
  )
}

const COHORT_BADGE_CLASS: Record<Cohort["status"], string> = {
  upcoming: "bg-info/15 text-info",
  active: "bg-success/15 text-success",
  completed: "bg-muted text-muted-foreground",
  archived: "bg-warning/15 text-warning",
}

export function CohortStatusBadge({ status }: { status: Cohort["status"] }) {
  return (
    <span
      className={`rounded-full px-1.5 py-0.5 text-[10px] font-medium ${COHORT_BADGE_CLASS[status]}`}
    >
      {status}
    </span>
  )
}
