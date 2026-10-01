import { formatNextUtcMidnight } from "@/i18n/format"
import { useCallback, useEffect, useMemo, useState } from "react"
import { useTranslation } from "react-i18next"
import { Link } from "react-router-dom"
import { ArrowRight, Flame, Sparkles } from "lucide-react"
import { toast } from "sonner"
import { getErrorCode } from "@/lib/errorCode"
import { cn } from "@/lib/utils"
import { Skeleton } from "@/components/ui/skeleton"
import { EmptyState, Eyebrow } from "@/components/patterns"
import { OptionButton, RevealPanel } from "@/components/dailyChallenge"
import {
  dailyChallengeService,
  type DailyChallengeAttemptResponse,
  type DailyChallengeTodayResponse,
} from "@/services/dailyChallenge"

interface RevealState {
  correct_option_id: string
  explanation: string | null
  is_correct: boolean
  streak_after: number
  selected_option_id: string
}

function revealFromAttempt(
  res: DailyChallengeAttemptResponse,
): RevealState {
  return {
    correct_option_id: res.correct_option_id,
    explanation: res.explanation,
    is_correct: res.is_correct,
    streak_after: res.streak_after,
    selected_option_id: res.selected_option_id,
  }
}

interface CandleStreakProps {
  count: number
  /** Answered today: the flame is lit. */
  lit: boolean
  label: string
}

/**
 * The streak, always on the card — «огонёк должен всегда быть показан».
 * An outline flame until today's question is answered, orange once it is;
 * the number is the run as of today, so a missed day shows 0 (the server
 * reads it that way, see `GET /daily-challenge/streak`). It used to appear
 * only after answering, so the one thing meant to bring a reader back was
 * invisible exactly when it could.
 */
function CandleStreak({ count, lit, label }: CandleStreakProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium tabular-nums transition-colors duration-base",
        lit ? "bg-warning/10 text-warning-ink" : "bg-surface/80 text-ink-muted",
      )}
      role="img"
      aria-label={label}
      title={label}
    >
      <Flame
        className={cn("h-3.5 w-3.5 transition-colors duration-base", lit ? "fill-warning text-warning" : "text-ink-muted")}
        strokeWidth={1.75}
        aria-hidden
      />
      <span>{count}</span>
    </span>
  )
}

/**
 * Today's Daily Challenge — one question for every user platform-wide.
 *
 * **States**
 *  - loading: skeleton lines
 *  - not scheduled (404 ``daily_challenge.not_scheduled``): muted empty
 *    state ("no question today"). The card stays mounted so the
 *    Dashboard grid keeps its layout, but the body switches.
 *  - not translated (404 ``daily_challenge.not_translated``): there is a
 *    question today, it just has not reached this language yet. Said out
 *    loud rather than hidden — the reader may well know somebody who
 *    already answered today's.
 *  - fresh: 4 option buttons, the user can pick one
 *  - already attempted: reveal-mode with the user's prior selection,
 *    the correct answer, the explanation, and the streak chip with
 *    the candle icon (🕯-style via lucide ``Flame``)
 *
 * Streak is rendered with ``CandleStreak`` — the candle/flame icon is
 * the agreed visual vocabulary for Daily Challenge streaks. The number
 * comes from the submit-attempt response when available, or from a
 * fallback ``getStreak`` call on already-attempted days.
 */
export function DailyChallengeCard() {
  const { t } = useTranslation()
  const [data, setData] = useState<DailyChallengeTodayResponse | null>(null)
  const [reveal, setReveal] = useState<RevealState | null>(null)
  const [loading, setLoading] = useState(true)
  const [notScheduled, setNotScheduled] = useState(false)
  // Scheduled, but not in this reader's language yet. A different state
  // from "no question today": there IS one, and everybody else can see
  // it. Saying so is the honest version of what used to render as an
  // empty question with four blank buttons.
  const [notTranslated, setNotTranslated] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [streakAfter, setStreakAfter] = useState<number | null>(null)
  const answeredToday = reveal !== null

  useEffect(() => {
    let cancelled = false
    const load = async () => {
      setLoading(true)
      try {
        // The streak alongside the question, answered or not: the chip is
        // on the card in every state now. Its failure costs the chip, not
        // the card.
        const [today, streak] = await Promise.all([
          dailyChallengeService.getToday(),
          dailyChallengeService.getStreak().catch(() => null),
        ])
        if (cancelled) return
        setData(today)
        setStreakAfter(streak?.current_streak ?? today.user_attempt?.streak_after ?? 0)
        if (today.user_attempt) {
          // Already answered → the same reveal the submit showed. The
          // server sends the correct option and the explanation for a
          // recorded attempt; before it did, a reload kept the chosen
          // option and lost the rest — no right answer after a wrong one,
          // no explanation after either.
          const attempt = today.user_attempt
          setReveal({
            correct_option_id:
              attempt.correct_option_id ?? (attempt.is_correct ? attempt.selected_option_id : ""),
            explanation: attempt.explanation ?? null,
            is_correct: attempt.is_correct,
            streak_after: attempt.streak_after,
            selected_option_id: attempt.selected_option_id,
          })
        }
      } catch (err) {
        if (cancelled) return
        const code = getErrorCode(err)
        if (code === "daily_challenge.not_scheduled") {
          setNotScheduled(true)
        } else if (code === "daily_challenge.not_translated") {
          setNotTranslated(true)
        } else {
          // The card is non-critical surface; log via toast and let
          // the empty-error state handle the render.
          toast.error(t("dailyChallenge.loadError"))
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [t])

  const handleSelect = useCallback(
    async (optionId: string) => {
      if (reveal !== null || submitting || !data) return
      setSubmitting(true)
      try {
        const res = await dailyChallengeService.submitAttempt(optionId)
        setReveal(revealFromAttempt(res))
        setStreakAfter(res.streak_after)
        if (res.is_correct) {
          toast.success(t("dailyChallenge.toast.correct"))
        } else {
          toast.message(t("dailyChallenge.toast.wrong"))
        }
      } catch (err) {
        const code = getErrorCode(err)
        if (code === "daily_challenge.invalid_option") {
          toast.error(t("dailyChallenge.toast.invalidOption"))
        } else {
          toast.error(t("dailyChallenge.toast.submitError"))
        }
      } finally {
        setSubmitting(false)
      }
    },
    [data, reveal, submitting, t],
  )

  const verseLabel = useMemo(() => {
    if (!data) return ""
    const range =
      data.bible_verse_from != null
        ? data.bible_verse_to != null && data.bible_verse_to !== data.bible_verse_from
          ? `${data.bible_verse_from}-${data.bible_verse_to}`
          : `${data.bible_verse_from}`
        : ""
    // The backend returns ``bible_book_label`` already localized per the
    // caller's ``Accept-Language`` (e.g. "Ин." for ru, "John" for en).
    return range
      ? `${data.bible_book_label} ${data.bible_chapter}:${range}`
      : `${data.bible_book_label} ${data.bible_chapter}`
  }, [data])

  return (
    <section
      aria-labelledby="dc-card-heading"
      className="surface-card animate-fade-in flex h-full flex-col overflow-hidden"
    >
      <header className="flex items-center justify-between gap-3 border-b border-edge bg-gradient-accent-subtle px-4 py-3 sm:px-5 sm:py-4">
        <div className="flex min-w-0 items-center gap-2.5">
          <Sparkles className="h-4 w-4 shrink-0 text-ink-muted" strokeWidth={1.75} aria-hidden />
          <div className="min-w-0">
            {/* The section's accessible name (and the e2e golden-path
                spec's anchor) has to stay put across every render state.
                It used to live on the element below, whose visible text
                swaps to the day's Bible reference once a question loads —
                a screen-reader user landing on "Rom. 8:1" with no heading
                anywhere that says "Daily Challenge" has lost the one word
                that says what card this is. The eyebrow's own copy is
                already that stable label in both languages, so it carries
                the id + heading role instead; sighted users see no change,
                the CSS is untouched. */}
            <Eyebrow as="h2" id="dc-card-heading">
              {t("dailyChallenge.eyebrow")}
            </Eyebrow>
            <p className="truncate font-serif text-sm font-semibold tracking-tight text-ink">
              {data ? verseLabel : t("dailyChallenge.title")}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {streakAfter != null && (
            <CandleStreak
              count={streakAfter}
              lit={answeredToday}
              label={
                answeredToday
                  ? t("dailyChallenge.streakAriaLabel", { count: streakAfter })
                  : t("dailyChallenge.streakPending", { count: streakAfter })
              }
            />
          )}
          <Link
            to="/daily-challenge/archive"
            className="inline-flex shrink-0 items-center gap-1 text-xs font-medium text-brand transition-opacity hover:opacity-80"
          >
            {/* The arrow alone on a phone; the word stays the link's name. */}
            <span className="max-sm:sr-only">{t("dailyChallenge.openArchive")}</span>
            <ArrowRight className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
          </Link>
        </div>
      </header>

      {/* Centred in the height the dashboard rail gives it: the rail shares
          its room between three cards, and this one may get more than it
          needs. */}
      <div className="flex min-h-0 flex-1 flex-col [justify-content:safe_center] gap-2.5 overflow-y-auto px-4 py-3 sm:px-5 sm:py-4">
        {loading ? (
          <div className="space-y-2">
            <Skeleton className="h-4 w-3/4" />
            <Skeleton className="h-3 w-full" />
            <Skeleton className="h-8 w-full" />
            <Skeleton className="h-8 w-full" />
            <Skeleton className="h-8 w-full" />
            <Skeleton className="h-8 w-full" />
          </div>
        ) : notScheduled ? (
          <EmptyState
            className="py-2"
            title={t("dailyChallenge.notScheduled.title")}
            description={t("dailyChallenge.notScheduled.body", { time: formatNextUtcMidnight() })}
          />
        ) : notTranslated ? (
          <EmptyState
            className="py-2"
            title={t("dailyChallenge.notTranslated.title")}
            description={t("dailyChallenge.notTranslated.body")}
          />
        ) : data ? (
          <>
            <p className="text-sm font-medium leading-snug text-ink">{data.question_text}</p>
            <ul className="space-y-1.5">
              {[...data.options]
                .sort((a, b) => a.order_index - b.order_index)
                .map((opt) => (
                  <li key={opt.id}>
                    <OptionButton
                      option={opt}
                      reveal={reveal}
                      disabled={reveal !== null || submitting}
                      onClick={() => void handleSelect(opt.id)}
                    />
                  </li>
                ))}
            </ul>
            {reveal !== null && (
              <RevealPanel isCorrect={reveal.is_correct} explanation={reveal.explanation} />
            )}
          </>
        ) : null}
      </div>
    </section>
  )
}
