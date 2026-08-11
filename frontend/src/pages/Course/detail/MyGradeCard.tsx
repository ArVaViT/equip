import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { CheckCircle2, Circle, Clock, HeartHandshake, Loader2, Undo2 } from "lucide-react"
import { gradesService } from "@/services/grades"
import type { MyCourseGrade, MyGradeItem } from "@/types"
import { myGradeDisplay, outstandingItems } from "./myGrade"

const ICON_BY_STATUS: Record<MyGradeItem["status"], typeof Circle> = {
  graded: CheckCircle2,
  pending_review: Clock,
  returned: Undo2,
  not_submitted: Circle,
  excused: HeartHandshake,
}

const TONE_BY_STATUS: Record<MyGradeItem["status"], string> = {
  graded: "text-success",
  pending_review: "text-warning",
  // The student's move, not the teacher's — coloured like something to act on.
  returned: "text-destructive",
  not_submitted: "text-ink-muted",
  excused: "text-info",
}

/**
 * The student's own grade, on their own course page.
 *
 * Until now this existed only behind a teacher login. A student saw a progress
 * bar and individual quiz scores, and had no way to answer "what am I getting
 * for this course" — which is the question they are actually asking, and the
 * one a refused certificate will one day answer for them.
 */
export function MyGradeCard({ courseId }: { courseId: string }) {
  const { t } = useTranslation()
  const [grade, setGrade] = useState<MyCourseGrade | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    gradesService
      .getMyCourseGrade(courseId)
      .then((g) => {
        if (!cancelled) setGrade(g)
      })
      // A course with nothing gradable in it has nothing to say here, and a
      // failed fetch is not worth an error box on somebody's course page —
      // the card simply does not appear.
      .catch(() => undefined)
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [courseId])

  if (loading) {
    return (
      <Card>
        <CardContent className="flex items-center gap-2 py-6 text-sm text-ink-muted">
          <Loader2 className="h-4 w-4 animate-spin" strokeWidth={1.75} aria-hidden />
          {t("myGrade.loading")}
        </CardContent>
      </Card>
    )
  }
  // An empty item list is not an empty card. A completion-only course has no
  // gradable work — and it is exactly the shape most certificates here have
  // come from, so a hand-set grade and the teacher's note to the student are
  // the only things that will ever appear on it.
  if (!grade) return null
  const hasAnythingToSay =
    grade.items.length > 0 || grade.official_grade !== null || grade.comment !== null
  if (!hasAnythingToSay) return null

  const display = myGradeDisplay(grade, t)
  const items = outstandingItems(grade.items)

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="font-serif text-lg">{t("myGrade.title")}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div>
          <p className="text-3xl font-bold tabular-nums">
            {display.headline ?? "—"}
            {display.isManual && (
              <span className="ml-2 align-middle text-xs font-medium text-info">
                {t("myGrade.setByTeacher")}
              </span>
            )}
          </p>
          {/* «Итоговая» appears the day it diverges — never for the first time
              when a certificate is refused (D10.1). */}
          {display.finalText && (
            <p className="mt-1 text-sm text-ink-muted">
              {t("myGrade.finalIs", { grade: display.finalText })} ·{" "}
              {t("gradebook.pair.explainer")}
            </p>
          )}
          {display.noteKey && <p className="mt-1 text-sm text-ink-muted">{t(display.noteKey)}</p>}
        </div>

        {/* The teacher's note written TO the student. The API has shipped this
            field all along and the app dropped it on the floor (D10.3). */}
        {grade.comment && (
          <blockquote className="border-l-2 border-info/40 bg-info/5 px-3 py-2 text-sm">
            {grade.comment}
          </blockquote>
        )}

        <ul className="space-y-1.5">
          {items.map((item) => {
            const Icon = ICON_BY_STATUS[item.status]
            return (
              // Keyed by item, not chapter: a chapter can hold two quizzes,
              // and keying by chapter collapsed them onto one row.
              <li key={item.item_id} className="flex items-center gap-2 text-sm">
                <Icon
                  className={`h-4 w-4 shrink-0 ${TONE_BY_STATUS[item.status]}`}
                  strokeWidth={1.75}
                  aria-hidden
                />
                <span className="flex-1 truncate">{item.title}</span>
                <span className="text-xs text-ink-muted">
                  {item.status === "graded" && item.score !== null
                    ? `${item.score.toFixed(0)}%`
                    : t(`myGrade.status.${item.status}`)}
                </span>
              </li>
            )
          })}
        </ul>
      </CardContent>
    </Card>
  )
}
