import { useCallback, useEffect, useMemo, useState } from "react"
import { useTranslation } from "react-i18next"
import { Link } from "react-router-dom"
import { ArrowRight, Flame, Sparkles } from "lucide-react"
import { toast } from "sonner"
import { getErrorCode } from "@/lib/errorCode"
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
  label: string
}

function CandleStreak({ count, label }: CandleStreakProps) {
  return (
    <span
      className="inline-flex items-center gap-1 rounded-full bg-surface/80 px-2 py-0.5 text-xs font-medium text-ink"
      aria-label={label}
    >
      <Flame className="h-3 w-3 text-brand" strokeWidth={1.75} aria-hidden />
      <span className="tabular-nums">{count}</span>
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
  const [submitting, setSubmitting] = useState(false)
  const [streakAfter, setStreakAfter] = useState<number | null>(null)

  useEffect(() => {
    let cancelled = false
    const load = async () => {
      setLoading(true)
      try {
        const today = await dailyChallengeService.getToday()
        if (cancelled) return
        setData(today)
        if (today.user_attempt) {
          // Reload the streak number so the chip reflects what the
          // backend currently shows — the attempt's stored streak is
          // the value *at submit time*, which may be stale once another
          // engagement happened in the same day.
          try {
            const streak = await dailyChallengeService.getStreak()
            if (!cancelled) setStreakAfter(streak.current_streak)
          } catch {
            if (!cancelled) setStreakAfter(today.user_attempt.streak_after)
          }
          // Already attempted → switch to reveal mode using the stored
          // selection. We don't have the canonical correct option id
          // until the user submits; for already-attempted days we
          // render the user's selected option as either correct (green)
          // or simply highlighted (neutral) based on ``is_correct``.
          setReveal({
            correct_option_id: today.user_attempt.is_correct
              ? today.user_attempt.selected_option_id
              : "", // empty so no option renders as green
            explanation: null,
            is_correct: today.user_attempt.is_correct,
            streak_after: today.user_attempt.streak_after,
            selected_option_id: today.user_attempt.selected_option_id,
          })
        }
      } catch (err) {
        if (cancelled) return
        if (getErrorCode(err) === "daily_challenge.not_scheduled") {
          setNotScheduled(true)
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
      className="surface-card animate-fade-in flex h-full flex-col overflow-hidden rounded-md"
    >
      <header className="flex items-center justify-between gap-3 border-b border-edge bg-gradient-accent-subtle px-4 py-3 sm:px-5 sm:py-4">
        <div className="flex min-w-0 items-center gap-2.5">
          <Sparkles className="h-4 w-4 shrink-0 text-ink-muted" strokeWidth={1.75} aria-hidden />
          <div className="min-w-0">
            <Eyebrow>{t("dailyChallenge.eyebrow")}</Eyebrow>
            <h2
              id="dc-card-heading"
              className="truncate font-serif text-sm font-semibold tracking-tight text-ink"
            >
              {data ? verseLabel : t("dailyChallenge.title")}
            </h2>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {streakAfter != null && (
            <CandleStreak count={streakAfter} label={t("dailyChallenge.streakAriaLabel", { count: streakAfter })} />
          )}
          <Link
            to="/daily-challenge/archive"
            className="inline-flex shrink-0 items-center gap-1 text-xs font-medium text-brand transition-opacity hover:opacity-80"
          >
            {t("dailyChallenge.openArchive")}
            <ArrowRight className="h-3 w-3" strokeWidth={1.75} aria-hidden />
          </Link>
        </div>
      </header>

      <div className="min-h-0 flex-1 space-y-2.5 overflow-y-auto px-4 py-3 sm:px-5 sm:py-4">
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
            description={t("dailyChallenge.notScheduled.body")}
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
