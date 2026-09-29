import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Award, CheckCircle2, ChevronDown, Circle, Clock, GraduationCap, HeartHandshake, Loader2, MessageSquareText, Undo2 } from "lucide-react"
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

  // Folded by default, and the fold says the essentials: the grade, how
  // much work is checked, whether the teacher wrote something, whether the
  // certificate is held back. Open, the card took a screen and a half of
  // the course page for what those four signs say in one line — «занимает
  // много места, надо значительно уменьшить».
  const expanded = openedByHand ?? false
  const counted = grade.items.filter((i) => i.status !== "excused")
  const checked = counted.filter((i) => i.status === "graded").length
  const blocked = grade.certificate_blockers.length > 0
  const setExpanded = (next: (open: boolean) => boolean) => setOpenedByHand(next(expanded))

  return (
    <Card>
      <CardHeader className="px-4 py-3 sm:px-5">
        <button
          type="button"
          onClick={() => setExpanded((open) => !open)}
          aria-expanded={expanded}
          className="flex w-full items-center justify-between gap-3 text-left"
        >
          <span className="flex min-w-0 items-center gap-2.5">
            <GraduationCap className="h-4 w-4 shrink-0 text-ink-muted" strokeWidth={1.75} aria-hidden />
            <CardTitle className="truncate font-serif text-base">{t("myGrade.title")}</CardTitle>
          </span>
          <span className="flex shrink-0 items-center gap-2 text-sm text-ink-muted">
            {display.headline !== null && (
              <span className="rounded-full bg-muted px-2.5 py-0.5 text-sm font-semibold tabular-nums text-ink">
                {display.headline}
              </span>
            )}
            {counted.length > 0 && (
              <span
                className="inline-flex items-center gap-1 text-xs tabular-nums"
                title={t("myGrade.summary.checked", { done: checked, total: counted.length })}
              >
                <CheckCircle2 className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
                {checked}/{counted.length}
                <span className="sr-only">{t("myGrade.summary.checked", { done: checked, total: counted.length })}</span>
              </span>
            )}
            {grade.comment && (
              <span title={t("myGrade.summary.hasComment")}>
                <MessageSquareText className="h-4 w-4 text-info" strokeWidth={1.75} aria-hidden />
                <span className="sr-only">{t("myGrade.summary.hasComment")}</span>
              </span>
            )}
            {blocked && (
              <span title={t("myGrade.certificate.notYetTitle")}>
                <Award className="h-4 w-4 text-warning" strokeWidth={1.75} aria-hidden />
                <span className="sr-only">{t("myGrade.certificate.notYetTitle")}</span>
              </span>
            )}
            <ChevronDown
              className={`h-4 w-4 shrink-0 transition-transform ${expanded ? "rotate-180" : ""}`}
              strokeWidth={1.75}
              aria-hidden
            />
          </span>
        </button>
      </CardHeader>
      <CardContent className={`space-y-3 px-4 pb-4 pt-0 sm:px-5 ${expanded ? "" : "hidden"}`}>
        {/* The number is in the header now; here only what explains it. */}
        {(display.isManual || display.finalText || display.noteKey) && (
          <div className="space-y-0.5 text-sm text-ink-muted">
            {display.isManual && <p className="text-xs font-medium text-info">{t("myGrade.setByTeacher")}</p>}
            {/* «Итоговая» appears the day it diverges — never for the first
                time when a certificate is refused (D10.1). */}
            {display.finalText && (
              <p>
                {t("myGrade.finalIs", { grade: display.finalText })} · {t("gradebook.pair.explainer")}
              </p>
            )}
            {display.noteKey && <p>{t(display.noteKey)}</p>}
          </div>
        )}

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

        <ul className="grid gap-x-6 gap-y-1.5 sm:grid-cols-2">
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
