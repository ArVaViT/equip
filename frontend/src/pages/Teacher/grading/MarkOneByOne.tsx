import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { Check, ChevronLeft, ChevronRight, FileText, Loader2, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Textarea } from "@/components/ui/textarea"
import { Input } from "@/components/ui/input"
import { RubricGrid } from "@/components/rubric/RubricGrid"
import { ErrorState, LateBadge } from "@/components/patterns"
import { rubricsService } from "@/services/rubrics"
import { coursesService } from "@/services/courses"
import { quizzesService } from "@/services/quizzes"
import { getErrorDetail } from "@/lib/errorDetail"
import { asPlainText } from "@/lib/plainText"
import { toast } from "@/lib/toast"
import { isHttpUrl } from "@/lib/url"
import { cn } from "@/lib/utils"
import { SubmissionFileChip } from "@/components/assignment/SubmissionFileChip"
import type { RubricMark, SubmissionRubric, WaitingWork } from "@/types"

/** A few ready words a teacher can tap instead of typing on a phone. Fixed on
 *  purpose: a comment bank with its own settings screen is a second thing to
 *  learn before marking the first essay. */
const COMMENT_BANK = ["coveredWell", "clearStructure", "addScripture", "moreExamples"] as const

/** Up to this many points the mark is a row of buttons, not a keyboard. */
const TAP_SCALE_MAX = 10

const NO_RUBRIC: SubmissionRubric = { rubric: null, marks: [], earned: null, out_of: null }

type Memory = { grade: number | null; feedback: string }
/** What the server holds for a piece this run has marked. `marks` is the
 *  chosen levels, for a rubric, as a stable string. */
type Saved = { grade: number | null; feedback: string; marks: string }

const marksKey = (marks: RubricMark[]) =>
  marks
    .map((m) => `${m.criterion_id}:${m.level_id}`)
    .sort()
    .join("|")

const isConflict = (err: unknown) =>
  typeof err === "object" && err !== null && (err as { response?: { status?: number } }).response?.status === 409

/**
 * Everything waiting, one piece at a time, across every course.
 *
 * The screen belongs to the work. Everything else — the mark, a ready
 * comment, the next button — is one tap away and nothing needs typing on a
 * phone unless the teacher wants to write something. A bivocational pastor
 * marking on Sunday evening is the case this has to survive; typing on a
 * phone is why marking gets postponed and then not done.
 *
 * «Дальше» is the primary action and it saves. With nothing chosen and
 * nothing written it moves on without saving, so one essay that needs a
 * second look does not hold up the other twenty. When it cannot go on, the
 * reason is written under it in plain words. «Назад» returns to the one
 * before, with the mark it was given; changing it saves again.
 *
 * There is no grading path of its own here: an open answer goes through the
 * quiz route, an assignment through the assignment or rubric route. Each is
 * sent once per «Дальше» — so the student hears once — and with
 * `expect_waiting` the first time, so work somebody else marked meanwhile is
 * refused rather than overwritten.
 */
export function MarkOneByOne({
  items,
  startAt = 0,
  onExit,
  onFinish,
  onMarked,
}: {
  items: WaitingWork[]
  startAt?: number
  onExit: () => void
  onFinish: () => void
  /** Called once per piece the first time it is marked here. */
  onMarked?: () => void
}) {
  const { t, i18n } = useTranslation()
  const [index, setIndex] = useState(() => Math.min(Math.max(startAt, 0), Math.max(items.length - 1, 0)))
  const [rubric, setRubric] = useState<SubmissionRubric | null>(null)
  // Empty until the teacher chooses a mark. It once started at 0, so saving
  // an essay nobody had scored sent the student a zero.
  const [grade, setGrade] = useState<number | null>(null)
  const [feedback, setFeedback] = useState("")
  const [saving, setSaving] = useState(false)
  // Level taps still on their way to the server. «Дальше» waits for them:
  // moving on with one in flight dropped its failure on the floor.
  const [levelsInFlight, setLevelsInFlight] = useState(0)
  const [rubricFailed, setRubricFailed] = useState(false)
  const [rubricAttempt, setRubricAttempt] = useState(0)
  const [, setLocalesLoaded] = useState(0)
  // What each piece of work was left with — typed, or saved — so «Назад»
  // returns to it as it was rather than blank.
  const memory = useRef(new Map<string, Memory>())
  // What the server holds, per piece this run has marked. State, not a ref:
  // the screen reads it to decide what the button does.
  const [saved, setSaved] = useState<Record<string, Saved>>({})
  // The marks as last chosen here, ahead of the server's answer. Two quick
  // taps on two criteria used to build the second request from the first's
  // not-yet-answered state — the second PUT then wrote only its own mark.
  const marksRef = useRef<RubricMark[]>([])
  const marksSeq = useRef(0)
  useEffect(() => {
    marksRef.current = rubric?.marks ?? []
  }, [rubric])

  // Ready comments are written to the student, so they go in the student's
  // language; those catalogues load lazily, like any language switch.
  const studentLocales = useMemo(() => [...new Set(items.map((i) => i.student_locale))], [items])
  useEffect(() => {
    void i18n.loadLanguages(studentLocales).then(() => setLocalesLoaded((n) => n + 1))
  }, [i18n, studentLocales])

  const current = items[index]
  const isLast = index + 1 >= items.length
  const before = current ? saved[current.id] : undefined

  useEffect(() => {
    if (!current) return
    const kept = memory.current.get(current.id)
    setGrade(kept?.grade ?? null)
    setFeedback(kept?.feedback ?? "")
  }, [current])

  const remember = (next: Partial<Memory>) => {
    if (!current) return
    const was = memory.current.get(current.id) ?? { grade, feedback }
    memory.current.set(current.id, { ...was, ...next })
  }

  useEffect(() => {
    if (!current) return
    marksSeq.current++
    setRubricFailed(false)
    if (current.kind !== "assignment") {
      setRubric(NO_RUBRIC)
      return
    }
    let cancelled = false
    setRubric(null)
    rubricsService
      .forSubmission(current.id)
      .then((r) => {
        if (!cancelled) setRubric(r)
      })
      .catch(() => {
        // Without an answer the screen would fall back to the bare number
        // box — and a number where the course uses a rubric is a different
        // mark than the teacher meant to give. Say so; skipping stays open.
        if (!cancelled) setRubricFailed(true)
      })
    return () => {
      cancelled = true
    }
  }, [current, rubricAttempt])

  const advance = useCallback(() => {
    if (isLast) onFinish()
    else setIndex((i) => i + 1)
  }, [isLast, onFinish])

  const onRubric = rubric?.rubric ?? null
  const criteriaCount = onRubric?.criteria.length ?? 0
  const chosenCount = onRubric
    ? onRubric.criteria.filter((c) => rubric?.marks.some((m) => m.criterion_id === c.id)).length
    : 0

  const chooseLevel = async (criterionId: string, levelId: string) => {
    if (!current || !onRubric) return
    const next: RubricMark[] = [
      ...marksRef.current.filter((m) => m.criterion_id !== criterionId),
      {
        criterion_id: criterionId,
        level_id: levelId,
        // The level's own points, so «Итого» is right before any answer —
        // the tap that completes the grid is not sent until «Дальше».
        points:
          onRubric.criteria.find((c) => c.id === criterionId)?.levels.find((l) => l.id === levelId)?.points ?? 0,
        comment: null,
      },
    ]
    marksRef.current = next
    setRubric((prev) => (prev ? { ...prev, marks: next } : prev))
    const complete = onRubric.criteria.every((c) => next.some((m) => m.criterion_id === c.id))
    // The tap that completes the grid is a mark: it goes with «Дальше» and
    // the note, in one request, so the student is told once and not twice.
    // Earlier taps still in flight are now older than what is on screen;
    // their answers must not put the grid back the way it was.
    const mine = ++marksSeq.current
    if (complete) return
    setLevelsInFlight((n) => n + 1)
    try {
      const result = await rubricsService.setMarks(
        current.id,
        next.map((m) => ({ criterion_id: m.criterion_id, level_id: m.level_id })),
        undefined,
        { expectWaiting: !before },
      )
      if (mine === marksSeq.current) setRubric(result)
    } catch (err) {
      // Every failure is said — a later tap carrying the same marks does not
      // make this one's refusal untrue.
      toast({ title: getErrorDetail(err, t("rubric.saveFailed")), variant: "destructive" })
      if (mine === marksSeq.current) setRubricAttempt((n) => n + 1)
    } finally {
      setLevelsInFlight((n) => n - 1)
    }
  }

  const rubricLoading = rubric === null && !rubricFailed
  const maxPoints = current?.max_points ?? null
  const note = feedback.trim()
  const overMax = maxPoints != null && grade != null && grade > maxPoints

  // What the button does, and when it cannot, why — in words under it.
  let action: "skip" | "save" | "wait" = "save"
  let hint: string | null = null
  if (rubricLoading || levelsInFlight > 0) {
    action = "wait"
  } else if (rubricFailed) {
    // Nothing can be marked without the rubric; the teacher can still move on.
    action = "skip"
  } else if (onRubric) {
    if (chosenCount === 0 && !note && !before) action = "skip"
    else if (chosenCount < criteriaCount) {
      action = "wait"
      hint = t("grading.hint.allCriteria", { done: chosenCount, total: criteriaCount })
    }
  } else if (grade === null) {
    if (!note && !before) action = "skip"
    else {
      // A note with no score would be dropped; a cleared saved score would
      // look removed while the server still holds it. Both ask for a score.
      action = "wait"
      hint = t("grading.hint.needScore")
    }
  } else if (overMax) {
    action = "wait"
    hint = t("grading.hint.notMore", { max: maxPoints })
  }

  const saveAndNext = async () => {
    if (!current || action === "wait") return
    if (action === "skip") {
      advance()
      return
    }
    const key = onRubric ? marksKey(rubric?.marks ?? []) : ""
    if (before && before.grade === grade && before.feedback === note && before.marks === key) {
      advance()
      return
    }
    const expectWaiting = !before
    setSaving(true)
    try {
      if (onRubric) {
        await rubricsService.setMarks(
          current.id,
          (rubric?.marks ?? []).map((m) => ({ criterion_id: m.criterion_id, level_id: m.level_id })),
          // Sent as written: an empty note clears the one sent before.
          note,
          { expectWaiting },
        )
      } else if (current.kind === "quiz_answer") {
        await quizzesService.gradeQuizAnswer(current.id, grade ?? 0, note || null, { expectWaiting })
      } else {
        await coursesService.gradeSubmission(current.id, {
          grade: grade ?? 0,
          feedback: note || undefined,
          status: "graded",
          expect_waiting: expectWaiting,
        })
      }
      if (!before) onMarked?.()
      setSaved((prev) => ({ ...prev, [current.id]: { grade, feedback: note, marks: key } }))
      advance()
    } catch (err) {
      if (isConflict(err)) {
        // Somebody marked it meanwhile. Theirs stands; the run goes on.
        toast({ title: t("grading.alreadyMarked") })
        advance()
      } else {
        toast({ title: getErrorDetail(err, t("grading.saveFailed")), variant: "destructive" })
      }
    } finally {
      setSaving(false)
    }
  }

  const back = () => {
    if (index > 0 && !saving && levelsInFlight === 0) setIndex((i) => i - 1)
  }

  const tStudent = current ? i18n.getFixedT(current.student_locale) : t
  const insertComment = (phrase: string) => {
    const next = feedback.trim() ? `${feedback.trimEnd()} ${phrase}` : phrase
    setFeedback(next)
    remember({ feedback: next })
  }

  if (!current) return null

  return (
    <div className="space-y-4 pb-36">
      <div className="flex items-center justify-between gap-3">
        <Button variant="ghost" size="sm" onClick={onExit} className="-ml-2 h-11">
          <X className="mr-1.5 h-4 w-4" strokeWidth={1.75} aria-hidden />
          {t("grading.toList")}
        </Button>
        {/* Where you are, so «дальше» is a known distance rather than an
            open-ended commitment on a Sunday evening. */}
        <span className="text-sm tabular-nums text-ink-muted">
          {t("grading.position", { n: index + 1, total: items.length })}
        </span>
      </div>
      <div className="h-1 overflow-hidden rounded-full bg-muted" aria-hidden>
        <div
          className="h-full rounded-full bg-brand transition-[width]"
          style={{ width: `${((index + 1) / items.length) * 100}%` }}
        />
      </div>

      <div>
        <p className="truncate text-xs text-ink-muted">{current.course_title}</p>
        <h2 className="line-clamp-2 break-words font-serif text-lg font-semibold">{current.title}</h2>
      </div>

      {/* What was asked: the question for an open answer, the instructions
          for an assignment. Work read without the ask cannot be judged. */}
      {current.prompt && (
        <p className="line-clamp-6 whitespace-pre-line rounded-md bg-surface-sunken px-4 py-3 font-serif text-base text-ink">
          {asPlainText(current.prompt)}
        </p>
      )}

      <Card>
        <CardContent className="space-y-3 p-4">
          <p className="flex items-center gap-2 text-sm font-medium">
            {current.student_name}
            {current.is_late && <LateBadge />}
          </p>
          {current.content && <div className="prose whitespace-pre-wrap text-wrap-safe">{current.content}</div>}
          {current.file_bucket && current.file_path && current.file_name && (
            <SubmissionFileChip bucket={current.file_bucket} path={current.file_path} name={current.file_name} />
          )}
          {current.file_url && isHttpUrl(current.file_url) && (
            <a
              href={current.file_url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex min-h-11 items-center gap-1.5 text-sm text-info hover:underline"
            >
              <FileText className="h-4 w-4 shrink-0" strokeWidth={1.75} aria-hidden />
              {t("assignmentEditor.grader.viewFile")}
            </a>
          )}
        </CardContent>
      </Card>

      {rubricFailed ? (
        <ErrorState
          className="py-6"
          title={t("rubric.loadFailed")}
          description={t("rubric.loadFailedBody")}
          action={
            <Button size="sm" variant="outline" onClick={() => setRubricAttempt((n) => n + 1)}>
              {t("common.tryAgain")}
            </Button>
          }
        />
      ) : rubricLoading ? (
        <div className="flex items-center gap-2 py-4 text-sm text-ink-muted">
          <Loader2 className="h-4 w-4 animate-spin" strokeWidth={1.75} aria-hidden />
          {t("common.loading")}
        </div>
      ) : onRubric ? (
        <Card>
          <CardContent className="p-4">
            <RubricGrid rubric={onRubric} marks={rubric?.marks ?? []} onChoose={chooseLevel} disabled={saving} />
          </CardContent>
        </Card>
      ) : maxPoints != null && maxPoints <= TAP_SCALE_MAX ? (
        <fieldset>
          <legend className="mb-2 text-sm font-medium">
            {t("grading.markLabel")}{" "}
            <span className="font-normal text-ink-muted">{t("grading.outOf", { max: maxPoints })}</span>
          </legend>
          <div className="flex flex-wrap gap-2">
            {Array.from({ length: maxPoints + 1 }, (_, n) => (
              <button
                key={n}
                type="button"
                aria-pressed={grade === n}
                onClick={() => {
                  // A saved score is changed by choosing another, never
                  // cleared by a second tap — that looked like removing the
                  // mark while the student still had it.
                  const next = grade === n && !before ? null : n
                  setGrade(next)
                  remember({ grade: next })
                }}
                className={cn(
                  "h-11 min-w-11 rounded-md border px-3 text-base font-medium tabular-nums transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand",
                  grade === n
                    ? "border-brand bg-brand text-brand-foreground"
                    : "border-edge-strong bg-surface hover:bg-heritage",
                )}
              >
                {n}
              </button>
            ))}
          </div>
        </fieldset>
      ) : (
        <label className="flex items-center gap-3">
          <span className="text-sm font-medium">{t("grading.markLabel")}</span>
          <Input
            type="number"
            inputMode="numeric"
            min={0}
            max={maxPoints ?? undefined}
            step={1}
            value={grade ?? ""}
            onChange={(e) => {
              const next = e.target.value === "" ? null : Math.max(0, Math.floor(Number(e.target.value) || 0))
              setGrade(next)
              remember({ grade: next })
            }}
            aria-invalid={overMax || undefined}
            className="h-12 w-24 text-lg aria-[invalid=true]:border-destructive"
            aria-label={t("grading.gradeAria")}
          />
          <span className="text-sm text-ink-muted">
            {maxPoints ? t("grading.outOf", { max: maxPoints }) : t("grading.points")}
          </span>
        </label>
      )}

      <div className="space-y-2">
        {/* Two by two: four short phrases fit a phone without a long column
            of pills between the work and the note. In the student's
            language — they are written to the student. */}
        <div className="grid grid-cols-2 gap-2">
          {COMMENT_BANK.map((key) => {
            const phrase = tStudent(`grading.commentBank.${key}`)
            const used = feedback.includes(phrase)
            return (
              <button
                key={key}
                type="button"
                disabled={used}
                onClick={() => insertComment(phrase)}
                className="flex min-h-11 items-center gap-1.5 rounded-lg border border-edge bg-surface px-3 py-2 text-left text-sm leading-snug text-ink transition-colors hover:bg-heritage focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:border-brand/30 disabled:bg-brand-quiet"
              >
                {used && <Check className="h-4 w-4 shrink-0 text-brand" strokeWidth={2} aria-hidden />}
                {phrase}
              </button>
            )
          })}
        </div>
        <Textarea
          value={feedback}
          onChange={(e) => {
            setFeedback(e.target.value)
            remember({ feedback: e.target.value })
          }}
          placeholder={t("grading.feedbackPlaceholder")}
          aria-label={t("grading.feedbackAria")}
          className="min-h-[88px] text-base"
        />
      </div>

      {/* Fixed to the bottom of the screen: the thumb finds «Дальше» in the
          same place on every essay. On a phone it sits on top of the tab bar
          (3.5rem, the same figure the page shell pads by), not under it. */}
      <div className="fixed inset-x-0 bottom-[calc(3.5rem+env(safe-area-inset-bottom))] z-30 border-t border-edge bg-surface/95 px-4 py-3 backdrop-blur md:bottom-0 md:pb-[max(0.75rem,env(safe-area-inset-bottom))]">
        <div className="mx-auto max-w-[680px]">
          {hint && (
            <p role="status" className="mb-2 text-center text-sm text-warning-ink">
              {hint}
            </p>
          )}
          <div className="flex gap-3">
            <Button
              variant="outline"
              onClick={back}
              disabled={index === 0 || saving || levelsInFlight > 0}
              className="h-12 px-4"
            >
              <ChevronLeft className="mr-1 h-4 w-4" strokeWidth={1.75} aria-hidden />
              {t("grading.back")}
            </Button>
            <Button
              onClick={saveAndNext}
              disabled={saving || action === "wait"}
              // Until a mark is chosen, choosing it is the main thing to do
              // on this screen; skipping is there, but it does not shout.
              variant={action === "skip" ? "outline" : "default"}
              className="h-12 flex-1 text-base"
            >
              {(saving || levelsInFlight > 0) && (
                <Loader2 className="mr-1.5 h-4 w-4 animate-spin" strokeWidth={1.75} aria-hidden />
              )}
              {action === "skip" ? t("grading.skip") : isLast ? t("grading.finish") : t("grading.next")}
              {!saving && !isLast && <ChevronRight className="ml-1 h-4 w-4" strokeWidth={1.75} aria-hidden />}
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}
