import { Link } from "react-router-dom"
import { useTranslation } from "react-i18next"
import { ArrowRight, Mail, UserRoundX } from "lucide-react"

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
        <h2 id="teacher-at-risk-heading" className="min-w-0 font-serif text-base font-semibold">
          {t("dashboard.atRisk.title")}
        </h2>
      </header>
      <ul className="divide-y divide-edge">
        {shown.map((s) => (
          <li key={`${s.course_id}:${s.student_id}`} className="flex items-center">
            <Link
              to={`/teacher/courses/${s.course_id}/progress`}
              className="flex min-w-0 flex-1 items-center justify-between gap-3 px-4 py-2.5 text-sm transition-colors hover:bg-muted/40 sm:px-5"
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
            {/* The point of the list: a word from the teacher. Beside the
                row, not inside it — a link inside a link is not allowed. */}
            {s.email && (
              <a
                href={`mailto:${encodeURIComponent(s.email).replace(/%40/g, "@")}?subject=${encodeURIComponent(s.course_title ?? "")}`}
                aria-label={t("dashboard.atRisk.write", { name: s.full_name })}
                className="mr-2 inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-md text-ink-muted transition-colors hover:bg-muted/40 hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand sm:mr-3"
              >
                <Mail className="h-4 w-4" strokeWidth={1.75} aria-hidden />
              </a>
            )}
          </li>
        ))}
      </ul>
      {rest > 0 && <p className="px-4 py-2 text-xs text-ink-muted sm:px-5">{t("dashboard.atRisk.more", { count: rest })}</p>}
    </section>
  )
}
