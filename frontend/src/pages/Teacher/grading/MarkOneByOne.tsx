import { useCallback, useEffect, useRef, useState } from "react"
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

/**
 * Everything waiting, one piece at a time, across every course.
 *
 * The screen belongs to the work. Everything else — the mark, a ready
 * comment, the next button — is one tap away and nothing needs typing on a
 * phone unless the teacher wants to write something. A bivocational pastor
 * marking on Sunday evening is the case this has to survive; typing on a
 * phone is why marking gets postponed and then not done.
 *
 * «Дальше» is the primary action and it saves. With nothing chosen it moves
 * on without saving, so one essay that needs a second look does not hold up
 * the other twenty. «Назад» returns to the one before, with the mark it was
 * given; changing it saves again through the same route.
 *
 * There is no grading path of its own here: an open answer goes through the
 * quiz route, an assignment through the assignment or rubric route, exactly as
 * they do from the course screens.
 */
export function MarkOneByOne({
  items,
  startAt = 0,
  onExit,
  onFinish,
}: {
  items: WaitingWork[]
  startAt?: number
  onExit: () => void
  onFinish: (marked: number) => void
}) {
  const { t } = useTranslation()
  const [index, setIndex] = useState(() => Math.min(Math.max(startAt, 0), Math.max(items.length - 1, 0)))
  const [rubric, setRubric] = useState<SubmissionRubric | null>(null)
  // Empty until the teacher chooses a mark. It once started at 0, so saving
  // an essay nobody had scored sent the student a zero.
  const [grade, setGrade] = useState<number | null>(null)
  const [feedback, setFeedback] = useState("")
  const [saving, setSaving] = useState(false)
  const [rubricFailed, setRubricFailed] = useState(false)
  const [rubricAttempt, setRubricAttempt] = useState(0)
  // What each piece of work was left with — typed, or saved — so «Назад»
  // returns to it as it was rather than blank.
  const memory = useRef(new Map<string, Memory>())
  // What the server holds, per piece: «Дальше» over an unchanged mark does
  // not send it twice.
  const saved = useRef(new Map<string, Memory>())
  // The marks as last chosen here, ahead of the server's answer. Two quick
  // taps on two criteria used to build the second request from the first's
  // not-yet-answered state — the second PUT then wrote only its own mark.
  const marksRef = useRef<RubricMark[]>([])
  const marksSeq = useRef(0)
  useEffect(() => {
    marksRef.current = rubric?.marks ?? []
  }, [rubric])

  const current = items[index]
  const isLast = index + 1 >= items.length

  // Each piece of work starts clean, or as the teacher left it. Carrying the
  // previous student's note into the next essay is the one mistake this
  // screen must never make. Only on a new piece of work, though: a rubric
  // retry must not wipe the note typed meanwhile.
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
    // A mark still in flight belongs to the previous piece of work; its
    // answer must not land on this one.
    marksSeq.current++
    setRubricFailed(false)
    if (current.kind !== "assignment") {
      // Open quiz answers are marked in points; there is no rubric to ask for.
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
        // mark than the teacher meant to give. Say so and wait.
        if (!cancelled) setRubricFailed(true)
      })
    return () => {
      cancelled = true
    }
  }, [current, rubricAttempt])

  const advance = useCallback(() => {
    if (isLast) onFinish(saved.current.size)
    else setIndex((i) => i + 1)
  }, [isLast, onFinish])

  const chooseLevel = async (criterionId: string, levelId: string) => {
    if (!current || !rubric?.rubric) return
    const next: RubricMark[] = [
      ...marksRef.current.filter((m) => m.criterion_id !== criterionId),
      { criterion_id: criterionId, level_id: levelId, points: 0, comment: null },
    ]
    marksRef.current = next
    // Shown at once; the points arrive with the server's answer.
    setRubric((prev) => (prev ? { ...prev, marks: next } : prev))
    const mine = ++marksSeq.current
    try {
      const result = await rubricsService.setMarks(
        current.id,
        next.map((m) => ({ criterion_id: m.criterion_id, level_id: m.level_id })),
        feedback.trim() || undefined,
      )
      // A later tap's request carries this mark too; its answer is the one to keep.
      if (mine !== marksSeq.current) return
      setRubric(result)
    } catch (err) {
      if (mine !== marksSeq.current) return
      toast({ title: getErrorDetail(err, t("rubric.saveFailed")), variant: "destructive" })
      // Back to what the server holds, not to what the screen hoped.
      setRubricAttempt((n) => n + 1)
    }
  }

  // Until the rubric answer arrives the screen cannot know which kind of
  // mark this work takes; a number typed in that moment would land where a
  // rubric was meant.
  const rubricLoading = rubric === null && !rubricFailed
  const maxPoints = current?.max_points ?? null
  const overMax = maxPoints != null && grade != null && grade > maxPoints
  // With a rubric the mark is the levels chosen: every criterion needs one.
  // Counted per criterion, not by number of marks: re-attaching a rubric keeps
  // the old one's marks, and they would make up the count.
  const onRubric = rubric?.rubric ?? null
  const rubricChosen = onRubric ? onRubric.criteria.filter((c) => rubric?.marks.some((m) => m.criterion_id === c.id)).length : 0
  const rubricIncomplete = onRubric != null && rubricChosen < onRubric.criteria.length
  // Nothing chosen at all: «Дальше» moves on and saves nothing.
  const untouched = !rubricLoading && (onRubric ? rubricChosen === 0 : grade === null)
  // Half-done — some criteria but not all, or a mark above the maximum —
  // is neither a mark nor a skip, so the button waits.
  const blocked = rubricLoading || rubricFailed || (!untouched && (rubricIncomplete || overMax))

  const saveAndNext = async () => {
    if (!current || blocked) return
    if (untouched) {
      advance()
      return
    }
    const note = feedback.trim()
    const before = saved.current.get(current.id)
    if (before && before.grade === grade && before.feedback === note) {
      advance()
      return
    }
    setSaving(true)
    try {
      if (onRubric) {
        // The rubric already wrote the mark as levels were chosen; this only
        // carries the note, and only if there is one.
        if (note || before) {
          await rubricsService.setMarks(
            current.id,
            (rubric?.marks ?? []).map((m) => ({ criterion_id: m.criterion_id, level_id: m.level_id })),
            note,
          )
        }
      } else if (current.kind === "quiz_answer") {
        await quizzesService.gradeQuizAnswer(current.id, grade ?? 0, note || null)
      } else {
        await coursesService.gradeSubmission(current.id, {
          grade: grade ?? 0,
          feedback: note || undefined,
          status: "graded",
        })
      }
      saved.current.set(current.id, { grade, feedback: note })
      advance()
    } catch (err) {
      toast({ title: getErrorDetail(err, t("grading.saveFailed")), variant: "destructive" })
    } finally {
      setSaving(false)
    }
  }

  const back = () => {
    if (index > 0 && !saving) setIndex((i) => i - 1)
  }

  const insertComment = (phrase: string) => {
    const next = feedback.trim() ? `${feedback.trimEnd()} ${phrase}` : phrase
    setFeedback(next)
    remember({ feedback: next })
  }

  if (!current) return null

  return (
    <div className="space-y-4 pb-28">
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
        <div className="h-full rounded-full bg-brand transition-[width]" style={{ width: `${((index + 1) / items.length) * 100}%` }} />
      </div>

      <div>
        <p className="truncate text-xs text-ink-muted">{current.course_title}</p>
        <h2 className="line-clamp-2 break-words font-serif text-lg font-semibold">{current.title}</h2>
      </div>

      {/* The question, for an open answer: an answer read without what was
          asked cannot be judged. */}
      {current.prompt && (
        <p className="rounded-md bg-surface-sunken px-4 py-3 font-serif text-base text-ink">{current.prompt}</p>
      )}

      <Card>
        <CardContent className="space-y-3 p-4">
          <p className="flex items-center gap-2 text-sm font-medium">
            {current.student_name}
            {current.is_late && <LateBadge />}
          </p>
          {/* The work gets the screen, and the same reading treatment the
              chapters get. */}
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
            {t("grading.markLabel")} <span className="font-normal text-ink-muted">{t("grading.outOf", { max: maxPoints })}</span>
          </legend>
          <div className="flex flex-wrap gap-2">
            {Array.from({ length: maxPoints + 1 }, (_, n) => (
              <button
                key={n}
                type="button"
                aria-pressed={grade === n}
                onClick={() => {
                  const next = grade === n ? null : n
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
            // Whole points: both grade routes take an integer.
            onChange={(e) => {
              const next = e.target.value === "" ? null : Math.max(0, Math.floor(Number(e.target.value) || 0))
              setGrade(next)
              remember({ grade: next })
            }}
            aria-invalid={overMax || undefined}
            className={cn("h-12 w-24 text-lg", overMax && "border-destructive")}
            aria-label={t("grading.gradeAria")}
          />
          <span className="text-sm text-ink-muted">
            {maxPoints ? t("grading.outOf", { max: maxPoints }) : t("grading.points")}
          </span>
        </label>
      )}

      <div className="space-y-2">
        {/* Two by two: four short phrases fit a phone without a long column
            of pills between the work and the note. */}
        <div className="grid grid-cols-2 gap-2">
          {COMMENT_BANK.map((key) => {
            const phrase = t(`grading.commentBank.${key}`)
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
          same place on every essay, however long the essay is. On a phone it
          sits on top of the tab bar (3.5rem, the same figure the page shell
          pads by), not under it. */}
      <div className="fixed inset-x-0 bottom-[calc(3.5rem+env(safe-area-inset-bottom))] z-30 border-t border-edge bg-surface/95 px-4 py-3 backdrop-blur md:bottom-0 md:pb-[max(0.75rem,env(safe-area-inset-bottom))]">
        <div className="mx-auto flex max-w-[680px] gap-3">
          <Button variant="outline" onClick={back} disabled={index === 0 || saving} className="h-12 px-4">
            <ChevronLeft className="mr-1 h-4 w-4" strokeWidth={1.75} aria-hidden />
            {t("grading.back")}
          </Button>
          <Button
            onClick={saveAndNext}
            disabled={saving || blocked}
            // Until a mark is chosen, choosing it is the main thing to do on
            // this screen; skipping is there, but it does not shout.
            variant={untouched ? "outline" : "default"}
            className="h-12 flex-1 text-base"
          >
            {saving && <Loader2 className="mr-1.5 h-4 w-4 animate-spin" strokeWidth={1.75} aria-hidden />}
            {untouched ? t("grading.skip") : isLast ? t("grading.finish") : t("grading.next")}
            {!saving && !isLast && <ChevronRight className="ml-1 h-4 w-4" strokeWidth={1.75} aria-hidden />}
          </Button>
        </div>
      </div>
    </div>
  )
}
