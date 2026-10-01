import { Link } from "react-router-dom"
import { useTranslation } from "react-i18next"
import { ArrowRight, UserRoundX } from "lucide-react"

import { useAuth } from "@/context/useAuth"
import { useAsyncData } from "@/hooks/useAsyncData"
import { canTeach } from "@/lib/roles"
import { orNotTranslated } from "@/lib/untranslated"
import { analyticsService, type StudentAtRisk } from "@/services/analytics"

const SHOWN = 5

/**
 * The students to write to this week: quiet for seven days, or two deadlines
 * missed with nothing handed in.
 *
 * Attrition in a free course is large and silent — nobody says they have
 * stopped — and a word from the teacher in the second week saves a student
 * where one in the fifth is a formality. Reading counts as activity: a
 * student reading every lesson is not on this list.
 *
 * A nudge, not an alarm: nothing at all when there is nobody, for students,
 * or when the request fails. Each row opens the course's progress board,
 * where the teacher can see the whole picture before writing.
 */
export function TeacherAtRiskCard() {
  const { t, i18n } = useTranslation()
  const { user } = useAuth()
  const teaches = canTeach(user?.role)
  const { data } = useAsyncData<StudentAtRisk[]>(
    async () => (teaches ? analyticsService.getStudentsAtRisk().catch(() => []) : []),
    [user?.id, teaches, i18n.language],
  )
  const list = data ?? []
  if (!teaches || list.length === 0) return null
  const shown = list.slice(0, SHOWN)
  const rest = list.length - shown.length

  return (
    <section
      aria-labelledby="teacher-at-risk-heading"
      className="animate-fade-in overflow-hidden rounded-card bg-card shadow-card"
    >
      <header className="flex items-center gap-3 border-b border-edge px-4 py-3 sm:px-5 sm:py-4">
        <UserRoundX className="h-4 w-4 shrink-0 text-ink-muted" strokeWidth={1.75} aria-hidden />
        <div className="min-w-0">
          <h2 id="teacher-at-risk-heading" className="font-serif text-base font-semibold">
            {t("dashboard.atRisk.title")}
          </h2>
          <p className="text-xs text-ink-muted">{t("dashboard.atRisk.hint")}</p>
        </div>
      </header>
      <ul className="divide-y divide-edge">
        {shown.map((s) => (
          <li key={`${s.course_id}:${s.student_id}`}>
            <Link
              to={`/teacher/courses/${s.course_id}/progress`}
              className="flex items-center justify-between gap-3 px-4 py-2.5 text-sm transition-colors hover:bg-muted/40 sm:px-5"
            >
              <span className="min-w-0">
                <span className="block truncate font-medium">{s.full_name}</span>
                <span className="block truncate text-xs text-ink-muted">
                  {orNotTranslated(t, s.course_title ?? "")}
                  {" · "}
                  {s.missed_deadlines >= 2
                    ? t("dashboard.atRisk.missed", { count: s.missed_deadlines })
                    : t("dashboard.atRisk.quiet", { count: s.quiet_days })}
                </span>
              </span>
              <ArrowRight className="h-4 w-4 shrink-0 text-ink-muted" strokeWidth={1.75} aria-hidden />
            </Link>
          </li>
        ))}
      </ul>
      {rest > 0 && <p className="px-4 py-2 text-xs text-ink-muted sm:px-5">{t("dashboard.atRisk.more", { count: rest })}</p>}
    </section>
  )
}
