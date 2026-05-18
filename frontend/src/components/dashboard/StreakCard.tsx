import { useTranslation } from "react-i18next"
import { Flame, Sparkles } from "lucide-react"
import { cn } from "@/lib/utils"

const DAYS_IN_WEEK = 7

// 0=Sun..6=Sat from getDay(); rotate so the row reads Mon..Sun (the
// week-start convention DESIGN.md uses elsewhere -- e.g. the calendar).
function todayIndexMonStart(): number {
  const sundayStart = new Date().getDay()
  return (sundayStart + 6) % DAYS_IN_WEEK
}

interface DayCellProps {
  abbr: string
  filled: boolean
  isToday: boolean
}

function DayCell({ abbr, filled, isToday }: DayCellProps) {
  return (
    <div className="flex min-w-0 flex-1 flex-col items-center gap-1.5">
      <span
        className={cn(
          "text-[10px] font-medium uppercase tracking-[0.18em]",
          isToday ? "text-foreground" : "text-muted-foreground",
        )}
      >
        {abbr}
      </span>
      {/* Dot. ``ring`` outlines today so the row reads as a week strip
          even when no day is "filled" yet; ``bg-primary`` is the lit
          flame state. Filled-and-today shows both. */}
      <span
        aria-hidden
        className={cn(
          "h-2.5 w-2.5 rounded-full transition-colors",
          filled ? "bg-primary" : "bg-muted",
          isToday && "ring-2 ring-primary/60 ring-offset-2 ring-offset-card",
        )}
      />
    </div>
  )
}

/**
 * Daily-streak placeholder for the new Dashboard.
 *
 * Skeleton on purpose -- the real "did you do today's tasks" logic
 * lands later. Today the card reserves the slot, sets the visual
 * vocabulary (week strip of 7 dots, today highlighted, task list
 * below), and shows a clear "coming soon" eyebrow so it can't be
 * mistaken for a finished feature.
 *
 * The task list below is intentionally text-only and disabled-looking
 * -- the items here are example/copy, not commitments. Replace with
 * real task data + interactivity in the follow-up PR.
 */
export function StreakCard() {
  const { t } = useTranslation()
  const today = todayIndexMonStart()
  const days = [
    t("streak.days.mon"),
    t("streak.days.tue"),
    t("streak.days.wed"),
    t("streak.days.thu"),
    t("streak.days.fri"),
    t("streak.days.sat"),
    t("streak.days.sun"),
  ]

  const tasks = [
    t("streak.tasksPreview.questionOfDay"),
    t("streak.tasksPreview.readChapter"),
    t("streak.tasksPreview.memoryVerse"),
  ]

  return (
    <section
      aria-labelledby="streak-card-heading"
      className="animate-fade-in overflow-hidden rounded-md border border-border bg-card"
    >
      <header className="border-b border-border bg-gradient-accent-subtle px-5 py-5 sm:px-6">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md border border-border/80 bg-card">
            <Flame className="h-5 w-5 text-muted-foreground" strokeWidth={1.75} aria-hidden />
          </div>
          <div className="min-w-0">
            <p className="text-[11px] font-medium uppercase tracking-[0.18em] text-muted-foreground">
              {t("streak.eyebrow")}
            </p>
            <h2
              id="streak-card-heading"
              className="font-serif text-lg font-semibold tracking-tight text-foreground"
            >
              {t("streak.title")}
            </h2>
          </div>
        </div>
      </header>

      <div className="space-y-5 px-5 py-5 sm:px-6 sm:py-6">
        {/* Week strip */}
        <div
          role="group"
          aria-label={t("streak.weekAriaLabel")}
          className="flex items-end gap-1"
        >
          {days.map((abbr, i) => (
            <DayCell key={i} abbr={abbr} filled={false} isToday={i === today} />
          ))}
        </div>

        {/* Today's tasks — example list */}
        <div>
          <p className="mb-2 text-xs font-medium uppercase tracking-[0.18em] text-muted-foreground">
            {t("streak.todayTasksLabel")}
          </p>
          <ul className="space-y-2">
            {tasks.map((label) => (
              <li
                key={label}
                className="flex items-center gap-2.5 text-sm text-muted-foreground"
              >
                <span
                  aria-hidden
                  className="h-3.5 w-3.5 shrink-0 rounded-full border border-border bg-background"
                />
                <span>{label}</span>
              </li>
            ))}
          </ul>
          <p className="mt-3 inline-flex items-center gap-1.5 text-xs text-muted-foreground/80">
            <Sparkles className="h-3.5 w-3.5 text-muted-foreground/60" strokeWidth={1.75} aria-hidden />
            {t("streak.comingSoon")}
          </p>
        </div>
      </div>
    </section>
  )
}
