import { useCallback, useEffect, useMemo, useState } from "react"
import { useTranslation } from "react-i18next"
import { useSearchParams } from "react-router-dom"
import { Calendar, Check, ChevronLeft, Sparkles, X } from "lucide-react"
import { toast } from "sonner"
import { cn } from "@/lib/utils"
import { getErrorCode } from "@/lib/errorCode"
import { PageHeader, EmptyState, ErrorState } from "@/components/patterns"
import { Skeleton } from "@/components/ui/skeleton"
import { Button } from "@/components/ui/button"
import {
  dailyChallengeService,
  type DailyChallengeArchiveEntry,
  type DailyChallengeArchiveQuestionResponse,
} from "@/services/dailyChallenge"

interface RevealState {
  correct_option_id: string
  explanation: string | null
  is_correct: boolean
  selected_option_id: string
}

/**
 * Archive of past Daily Challenge questions. Calendar grid of recent
 * scheduled dates; clicking a cell loads the question detail panel
 * on the right with reveal-mode when the user has attempted before
 * or after they submit a replay.
 *
 * Replays do NOT touch the streak (the backend writes
 * ``is_archive=true`` so the YouVersion streak math skips them).
 * The detail panel makes that explicit via the replay badge.
 */
export default function DailyChallengeArchivePage() {
  const { t } = useTranslation()
  const [searchParams, setSearchParams] = useSearchParams()

  const [entries, setEntries] = useState<DailyChallengeArchiveEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState(false)
  const [nextCursor, setNextCursor] = useState<string | null>(null)
  const [loadingMore, setLoadingMore] = useState(false)

  const selectedDate = searchParams.get("d")

  const loadInitial = useCallback(async () => {
    setLoading(true)
    setLoadError(false)
    try {
      const list = await dailyChallengeService.listArchive()
      setEntries(list.entries)
      setNextCursor(list.next_cursor)
    } catch {
      setLoadError(true)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadInitial()
  }, [loadInitial])

  const loadEarlier = useCallback(async () => {
    if (!nextCursor || loadingMore) return
    setLoadingMore(true)
    try {
      const list = await dailyChallengeService.listArchive(nextCursor)
      setEntries((prev) => [...prev, ...list.entries])
      setNextCursor(list.next_cursor)
    } catch {
      toast.error(t("dailyChallenge.archive.loadError"))
    } finally {
      setLoadingMore(false)
    }
  }, [nextCursor, loadingMore, t])

  const selectDate = (date: string | null) => {
    const next = new URLSearchParams(searchParams)
    if (date) next.set("d", date)
    else next.delete("d")
    setSearchParams(next, { replace: false })
  }

  const correctCount = entries.filter((e) => e.attempted_is_correct === true).length
  const attemptedCount = entries.filter((e) => e.attempted_is_correct !== null).length

  return (
    <div className="container mx-auto max-w-6xl px-4 py-6 sm:py-8">
      <PageHeader
        title={
          <h1 className="flex items-center gap-2 font-serif text-2xl font-bold tracking-tight sm:text-3xl">
            <Sparkles className="h-6 w-6 text-primary" strokeWidth={1.75} aria-hidden />
            {t("dailyChallenge.archive.title")}
          </h1>
        }
        description={
          <p className="text-sm text-muted-foreground">
            {t("dailyChallenge.archive.description")}
          </p>
        }
      />

      <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,360px)]">
        <section
          aria-labelledby="dc-archive-grid-heading"
          className="rounded-md border border-border bg-card"
        >
          <header className="flex items-center justify-between gap-3 border-b border-border bg-gradient-accent-subtle px-4 py-3 sm:px-5 sm:py-4">
            <div className="flex items-center gap-2.5">
              <Calendar
                className="h-4 w-4 shrink-0 text-muted-foreground"
                strokeWidth={1.75}
                aria-hidden
              />
              <h2
                id="dc-archive-grid-heading"
                className="font-serif text-sm font-semibold tracking-tight text-foreground"
              >
                {t("dailyChallenge.archive.gridHeading")}
              </h2>
            </div>
            {!loading && !loadError && entries.length > 0 && (
              <div className="text-xs tabular-nums text-muted-foreground">
                {t("dailyChallenge.archive.gridStats", {
                  correct: correctCount,
                  attempted: attemptedCount,
                })}
              </div>
            )}
          </header>

          <div className="px-4 py-3 sm:px-5 sm:py-4">
            {loading ? (
              <div className="grid grid-cols-7 gap-2">
                {Array.from({ length: 28 }).map((_, i) => (
                  <Skeleton key={i} className="h-10 w-full" />
                ))}
              </div>
            ) : loadError ? (
              <ErrorState
                className="py-4"
                title={t("dailyChallenge.archive.loadError")}
                action={
                  <Button size="sm" variant="outline" onClick={loadInitial}>
                    {t("common.tryAgain")}
                  </Button>
                }
              />
            ) : entries.length === 0 ? (
              <EmptyState
                variant="compact"
                title={t("dailyChallenge.archive.empty.title")}
                description={t("dailyChallenge.archive.empty.body")}
              />
            ) : (
              <>
                <CalendarGrid
                  entries={entries}
                  selectedDate={selectedDate}
                  onSelect={selectDate}
                  t={t}
                />
                {nextCursor && (
                  <div className="mt-4 flex justify-center">
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={loadEarlier}
                      disabled={loadingMore}
                    >
                      {loadingMore
                        ? t("common.loading")
                        : t("dailyChallenge.archive.loadEarlier")}
                    </Button>
                  </div>
                )}
              </>
            )}
          </div>
        </section>

        <DetailPanel
          challengeDate={selectedDate}
          onBack={() => selectDate(null)}
          t={t}
        />
      </div>
    </div>
  )
}

interface CalendarGridProps {
  entries: DailyChallengeArchiveEntry[]
  selectedDate: string | null
  onSelect: (date: string) => void
  t: (key: string, opts?: Record<string, unknown>) => string
}

function CalendarGrid({ entries, selectedDate, onSelect, t }: CalendarGridProps) {
  // Group entries by month so the grid reads as time, not as a tag soup.
  const byMonth = useMemo(() => {
    const groups: Record<string, DailyChallengeArchiveEntry[]> = {}
    for (const e of entries) {
      const key = e.challenge_date.slice(0, 7) // YYYY-MM
      ;(groups[key] ??= []).push(e)
    }
    return groups
  }, [entries])

  const months = Object.keys(byMonth).sort().reverse()

  return (
    <div className="space-y-5">
      {months.map((monthKey) => {
        const monthEntries = byMonth[monthKey] ?? []
        const monthLabel = new Date(`${monthKey}-01T00:00:00Z`).toLocaleDateString(
          undefined,
          { year: "numeric", month: "long" },
        )
        return (
          <div key={monthKey} className="space-y-2">
            <p className="text-[11px] font-medium uppercase tracking-[0.18em] text-muted-foreground">
              {monthLabel}
            </p>
            <div className="grid grid-cols-7 gap-1.5 sm:gap-2">
              {monthEntries
                .slice()
                .sort((a, b) => a.challenge_date.localeCompare(b.challenge_date))
                .map((entry) => (
                  <DayCell
                    key={entry.challenge_date}
                    entry={entry}
                    selected={selectedDate === entry.challenge_date}
                    onSelect={() => onSelect(entry.challenge_date)}
                    t={t}
                  />
                ))}
            </div>
          </div>
        )
      })}
    </div>
  )
}

interface DayCellProps {
  entry: DailyChallengeArchiveEntry
  selected: boolean
  onSelect: () => void
  t: (key: string, opts?: Record<string, unknown>) => string
}

function DayCell({ entry, selected, onSelect, t }: DayCellProps) {
  const correct = entry.attempted_is_correct === true
  const wrong = entry.attempted_is_correct === false
  const replay = entry.archive_only_attempt
  const day = entry.challenge_date.slice(-2).replace(/^0/, "")
  const status = correct
    ? t("dailyChallenge.archive.cellStatus.correct")
    : wrong
      ? t("dailyChallenge.archive.cellStatus.wrong")
      : t("dailyChallenge.archive.cellStatus.notAttempted")

  return (
    <button
      type="button"
      onClick={onSelect}
      aria-pressed={selected}
      aria-label={t("dailyChallenge.archive.cellAriaLabel", {
        date: entry.challenge_date,
        status,
      })}
      className={cn(
        "group relative flex h-10 flex-col items-center justify-center rounded-md border text-[11px] font-medium tabular-nums transition-colors",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40",
        correct && !replay && "border-success/50 bg-success/15 text-foreground",
        correct && replay && "border-success/30 bg-success/5 text-foreground",
        wrong && !replay && "border-destructive/40 bg-destructive/10 text-foreground",
        wrong && replay && "border-destructive/30 bg-destructive/5 text-foreground",
        !correct && !wrong && "border-border bg-muted/30 text-muted-foreground",
        selected && "ring-2 ring-primary ring-offset-1 ring-offset-card",
      )}
    >
      <span>{day}</span>
      {(correct || wrong) && (
        <span
          aria-hidden
          className={cn(
            "absolute right-0.5 top-0.5 flex h-3 w-3 items-center justify-center rounded-full",
            correct ? "bg-success text-success-foreground" : "bg-destructive text-destructive-foreground",
          )}
        >
          {correct ? <Check className="h-2 w-2" strokeWidth={2.5} /> : <X className="h-2 w-2" strokeWidth={2.5} />}
        </span>
      )}
    </button>
  )
}

interface DetailPanelProps {
  challengeDate: string | null
  onBack: () => void
  t: (key: string, opts?: Record<string, unknown>) => string
}

function DetailPanel({ challengeDate, onBack, t }: DetailPanelProps) {
  const [data, setData] = useState<DailyChallengeArchiveQuestionResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [reveal, setReveal] = useState<RevealState | null>(null)
  const [notScheduled, setNotScheduled] = useState(false)
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    if (!challengeDate) {
      setData(null)
      setReveal(null)
      setNotScheduled(false)
      return
    }
    let cancelled = false
    setLoading(true)
    setNotScheduled(false)
    setReveal(null)
    void dailyChallengeService
      .getArchiveQuestion(challengeDate)
      .then((res) => {
        if (cancelled) return
        setData(res)
        if (res.reveal) {
          setReveal({
            correct_option_id: res.reveal.correct_option_id,
            explanation: res.reveal.explanation,
            is_correct: res.reveal.last_attempt_was_correct,
            selected_option_id: "",
          })
        }
      })
      .catch((err) => {
        if (cancelled) return
        const code = getErrorCode(err)
        if (code === "daily_challenge.not_scheduled") {
          setNotScheduled(true)
        } else if (code === "daily_challenge.archive_date_not_allowed") {
          toast.error(t("dailyChallenge.archive.toast.dateNotAllowed"))
        } else {
          toast.error(t("dailyChallenge.archive.loadError"))
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [challengeDate, t])

  const handleSelect = useCallback(
    async (optionId: string) => {
      if (!data || reveal !== null || submitting) return
      setSubmitting(true)
      try {
        const res = await dailyChallengeService.submitArchiveAttempt(
          data.challenge_date,
          optionId,
        )
        setReveal({
          correct_option_id: res.correct_option_id,
          explanation: res.explanation,
          is_correct: res.is_correct,
          selected_option_id: res.selected_option_id,
        })
        if (res.is_correct) toast.success(t("dailyChallenge.archive.toast.correct"))
        else toast.message(t("dailyChallenge.archive.toast.wrong"))
      } catch (err) {
        const code = getErrorCode(err)
        if (code === "daily_challenge.invalid_option") {
          toast.error(t("dailyChallenge.archive.toast.invalidOption"))
        } else {
          toast.error(t("dailyChallenge.archive.toast.submitError"))
        }
      } finally {
        setSubmitting(false)
      }
    },
    [data, reveal, submitting, t],
  )

  if (!challengeDate) {
    return (
      <section className="rounded-md border border-border bg-card p-6 text-center">
        <EmptyState
          variant="compact"
          title={t("dailyChallenge.archive.detail.pickDate")}
          description={t("dailyChallenge.archive.detail.pickDateHint")}
        />
      </section>
    )
  }

  return (
    <section
      aria-labelledby="dc-archive-detail-heading"
      className="rounded-md border border-border bg-card"
    >
      <header className="flex items-center gap-2.5 border-b border-border bg-gradient-accent-subtle px-4 py-3 sm:px-5 sm:py-4">
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={onBack}
          aria-label={t("dailyChallenge.archive.detail.back")}
          className="-ml-2 h-7 w-7 p-0"
        >
          <ChevronLeft className="h-4 w-4" strokeWidth={1.75} aria-hidden />
        </Button>
        <h2
          id="dc-archive-detail-heading"
          className="font-serif text-sm font-semibold tracking-tight text-foreground"
        >
          {data
            ? `${data.bible_book_label} ${data.bible_chapter}${
                data.bible_verse_from != null
                  ? `:${data.bible_verse_from}${
                      data.bible_verse_to && data.bible_verse_to !== data.bible_verse_from
                        ? `-${data.bible_verse_to}`
                        : ""
                    }`
                  : ""
              }`
            : challengeDate}
        </h2>
        <span className="ml-auto text-[11px] uppercase tracking-[0.14em] text-muted-foreground">
          {t("dailyChallenge.archive.detail.replayBadge")}
        </span>
      </header>

      <div className="space-y-3 px-4 py-3 sm:px-5 sm:py-4">
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
            variant="compact"
            title={t("dailyChallenge.archive.notScheduled.title")}
            description={t("dailyChallenge.archive.notScheduled.body")}
          />
        ) : data ? (
          <>
            <p className="text-sm font-medium leading-snug text-foreground">{data.question_text}</p>
            <ul className="space-y-1.5">
              {[...data.options]
                .sort((a, b) => a.order_index - b.order_index)
                .map((opt) => {
                  const isCorrect = reveal?.correct_option_id === opt.id
                  const isSelected = reveal?.selected_option_id === opt.id
                  const showCorrect = reveal !== null && isCorrect
                  const showWrong = reveal !== null && isSelected && !isCorrect
                  return (
                    <li key={opt.id}>
                      <button
                        type="button"
                        onClick={() => void handleSelect(opt.id)}
                        disabled={reveal !== null || submitting}
                        aria-pressed={isSelected}
                        className={cn(
                          "flex w-full items-center gap-2.5 rounded-md border px-3 py-2 text-left text-xs transition-colors",
                          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40",
                          reveal === null && "border-border bg-background hover:border-primary/30 hover:bg-muted/30",
                          showCorrect && "border-success/40 bg-success/10 text-foreground",
                          showWrong && "border-destructive/40 bg-destructive/10 text-foreground",
                          reveal !== null && !showCorrect && !showWrong && "border-border bg-background text-muted-foreground",
                          (reveal !== null || submitting) && "cursor-default",
                        )}
                      >
                        <span
                          aria-hidden
                          className={cn(
                            "flex h-5 w-5 shrink-0 items-center justify-center rounded-full border text-[10px] font-semibold",
                            reveal === null && "border-border text-muted-foreground",
                            showCorrect && "border-success bg-success text-success-foreground",
                            showWrong && "border-destructive bg-destructive text-destructive-foreground",
                            reveal !== null && !showCorrect && !showWrong && "border-border text-muted-foreground",
                          )}
                        >
                          {showCorrect ? (
                            <Check className="h-3 w-3" strokeWidth={1.75} />
                          ) : showWrong ? (
                            <X className="h-3 w-3" strokeWidth={1.75} />
                          ) : (
                            String.fromCharCode(65 + opt.order_index)
                          )}
                        </span>
                        <span className="min-w-0 flex-1 truncate">{opt.option_text}</span>
                      </button>
                    </li>
                  )
                })}
            </ul>
            {reveal !== null && (
              <div className="space-y-1.5 rounded-md border border-border/80 bg-muted/20 px-3 py-2.5">
                <p
                  className={cn(
                    "text-[11px] font-semibold uppercase tracking-[0.14em]",
                    reveal.is_correct ? "text-success" : "text-muted-foreground",
                  )}
                >
                  {reveal.is_correct
                    ? t("dailyChallenge.reveal.correct")
                    : t("dailyChallenge.reveal.wrong")}
                </p>
                {reveal.explanation && (
                  <p className="text-xs leading-snug text-foreground">{reveal.explanation}</p>
                )}
              </div>
            )}
          </>
        ) : null}
      </div>
    </section>
  )
}
