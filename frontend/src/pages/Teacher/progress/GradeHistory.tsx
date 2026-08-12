import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { History, Loader2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { gradesService } from "@/services/grades"
import { formatDate } from "@/i18n/format"
import type { GradeHistoryEntry } from "@/types"

/** Actions this build has words for. See the fallback below for the rest. */
const NAMED_ACTIONS = new Set([
  "grade_override_set",
  "grade_override_changed",
  "grade_override_cleared",
  "grade_exemption_created",
  "grade_exemption_removed",
  "retake_request",
])

/**
 * How this student's grade came to be what it is (D7).
 *
 * A hand-set grade is the one number on this page nobody can reconstruct from
 * the work. Six months later, when a director signs a ведомость, "why is this
 * a B when the system computed 64" needs an answer that is not somebody's
 * memory. The rows have been written since Phase 1; nothing has ever read them.
 *
 * Loaded on demand rather than with the row: most students never have a
 * history, and paying for the query on every expansion to show "nothing
 * happened" is how a board gets slow.
 */
export function GradeHistory({ courseId, studentId }: { courseId: string; studentId: string }) {
  const { t } = useTranslation()
  const [entries, setEntries] = useState<GradeHistoryEntry[] | null>(null)
  const [loading, setLoading] = useState(false)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    // A different student in the same open drawer must not inherit the last
    // one's history — the worst possible failure on a screen about who did
    // what to whose grade.
    setEntries(null)
    setFailed(false)
  }, [courseId, studentId])

  const load = async () => {
    setLoading(true)
    setFailed(false)
    try {
      setEntries(await gradesService.getGradeHistory(courseId, studentId))
    } catch {
      setFailed(true)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div>
      <h4 className="mb-2 flex items-center gap-1.5 text-sm font-semibold">
        <History className="h-4 w-4" strokeWidth={1.75} aria-hidden />
        {t("studentProgress.history.title")}
      </h4>
      {entries === null ? (
        <Button size="sm" variant="outline" onClick={load} disabled={loading}>
          {loading && <Loader2 className="mr-1.5 h-4 w-4 animate-spin" strokeWidth={1.75} aria-hidden />}
          {failed ? t("studentProgress.history.retry") : t("studentProgress.history.show")}
        </Button>
      ) : entries.length === 0 ? (
        // A true and useful answer, and the one most students get.
        <p className="text-sm text-ink-muted">{t("studentProgress.history.empty")}</p>
      ) : (
        <ol className="space-y-2">
          {entries.map((entry) => (
            <li key={entry.id} className="border-l-2 border-ink-muted/25 pl-3 text-sm">
              <p>
                {t(
                  NAMED_ACTIONS.has(entry.action)
                    ? `studentProgress.history.action.${entry.action}`
                    : "studentProgress.history.action.unknown",
                  { grade: entry.override_code ?? entry.override_score ?? "" },
                )}
                {/* "Teacher set B" says little. "Teacher set B where the system
                    had computed 64%" is the sentence a director needs. */}
                {entry.computed_score !== null && entry.computed_score !== undefined && (
                  <span className="text-ink-muted">
                    {" "}
                    {t("studentProgress.history.computedWas", { score: entry.computed_score })}
                  </span>
                )}
              </p>
              <p className="text-xs text-ink-muted">
                {entry.actor_name ?? t("studentProgress.history.unknownActor")} ·{" "}
                {formatDate(entry.at)}
              </p>
              {entry.reason && (
                // The note written for the institution (D7). It never reaches
                // the student; this screen is what it was written for.
                <p className="mt-0.5 text-sm italic text-ink-muted">{entry.reason}</p>
              )}
            </li>
          ))}
        </ol>
      )}
    </div>
  )
}
