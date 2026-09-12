import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { CheckCircle2, ChevronDown, Circle, Clock, HeartHandshake, Loader2, Undo2 } from "lucide-react"
import { gradesService } from "@/services/grades"
import type { CourseStructure } from "@/lib/courseStructure"
import type { MyCourseGrade, MyGradeItem } from "@/types"
import { CertificateBlockers } from "./CertificateBlockers"
import { myGradeDisplay, outstandingItems } from "./myGrade"
import { orNotTranslated } from "@/lib/untranslated"
import { formatPercent } from "@/i18n/number"

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
export function MyGradeCard({
  courseId,
  structure,
  onBlockersChange,
}: {
  courseId: string
  /** The course's lessons, so a blocker can be named and linked to. */
  structure: CourseStructure
  /** Reported upward so the certificate card below can stop offering a button
   *  whose only outcome is an error. Lifted rather than fetched twice: the two
   *  cards must agree, and two fetches is how they stop agreeing. */
  onBlockersChange?: (count: number) => void
}) {
  const { t } = useTranslation()
  const [grade, setGrade] = useState<MyCourseGrade | null>(null)
  const [loading, setLoading] = useState(true)
  // ``null`` until the grade arrives and decides the default; a person
  // who opens or closes it keeps their choice from then on.
  const [openedByHand, setOpenedByHand] = useState<boolean | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    gradesService
      .getMyCourseGrade(courseId)
      .then((g) => {
        if (cancelled) return
        setGrade(g)
        onBlockersChange?.(g.certificate_blockers.length)
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
  }, [courseId, onBlockersChange])

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
    grade.items.length > 0 ||
    grade.official_grade !== null ||
    grade.comment !== null ||
    grade.certificate_blockers.length > 0
  if (!hasAnythingToSay) return null

  const display = myGradeDisplay(grade, t)
  const items = outstandingItems(grade.items)

  // Open when there is something to read, folded when there is not.
  // On a course somebody just joined this card says "graded on
  // completion, 0%" and takes a screenful to say it; on a course with a
  // mark and a teacher's note, hiding it would bury the one thing the
  // student came to see.
  const worthOpening = display.headline !== null || grade.comment !== null
  const expanded = openedByHand ?? worthOpening
  const setExpanded = (next: (open: boolean) => boolean) => setOpenedByHand(next(expanded))

  return (
    <Card>
      <CardHeader className="pb-3">
        <button
          type="button"
          onClick={() => setExpanded((open) => !open)}
          aria-expanded={expanded}
          className="flex w-full items-center justify-between gap-2 text-left"
        >
          <CardTitle className="font-serif text-lg">{t("myGrade.title")}</CardTitle>
          <span className="flex items-center gap-2 text-sm text-ink-muted">
            {!expanded && display.headline !== null && (
              <span className="font-medium tabular-nums text-ink">{display.headline}</span>
            )}
            <ChevronDown
              className={`h-4 w-4 shrink-0 transition-transform ${expanded ? "rotate-180" : ""}`}
              strokeWidth={1.75}
              aria-hidden
            />
          </span>
        </button>
      </CardHeader>
      <CardContent className={`space-y-4 ${expanded ? "" : "hidden"}`}>
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

        {/* Directly above the item list, and directly above the certificate
            card on the page: the student reads what is missing, then sees
            which item it is, then meets the button. */}
        <CertificateBlockers
          blockers={grade.certificate_blockers}
          structure={structure}
          courseId={courseId}
        />

        <ul className="space-y-1.5">
          {items.map((item) => {
            const Icon = ICON_BY_STATUS[item.status]
            return (
              // Keyed by item, not chapter: a chapter can hold two quizzes,
              // and keying by chapter collapsed them onto one row.
              <li key={item.item_id} className="text-sm">
                <div className="flex items-center gap-2">
                  <Icon
                    className={`h-4 w-4 shrink-0 ${TONE_BY_STATUS[item.status]}`}
                    strokeWidth={1.75}
                    aria-hidden
                  />
                  <span className="flex-1 truncate">{orNotTranslated(t, item.title)}</span>
                  <span className="text-xs text-ink-muted">
                    {item.status === "graded" && item.score !== null
                      ? formatPercent(item.score, 0)
                      : t(`myGrade.status.${item.status}`)}
                  </span>
                </div>
                {/* The number without the words is the grade without the
                    lesson. It was always stored and always two navigations
                    away; this is the screen the student actually opens. */}
                {item.feedback && (
                  <p className="ml-6 mt-1 border-l-2 border-ink-muted/25 pl-2 text-sm text-ink-muted">
                    {item.feedback}
                  </p>
                )}
              </li>
            )
          })}
        </ul>
      </CardContent>
    </Card>
  )
}
