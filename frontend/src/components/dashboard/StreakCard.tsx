import { useTranslation } from "react-i18next"
import { Flame, Sparkles } from "lucide-react"
import { cn } from "@/lib/utils"

const DAYS_IN_WEEK = 7

// 0=Sun..6=Sat from getDay(); rotate so the row reads Mon..Sun, the
// week-start convention used elsewhere (Calendar, MiniCalendar).
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
    <div className="flex min-w-0 flex-1 flex-col items-center gap-1">
      <span
        className={cn(
          "text-[10px] font-medium uppercase tracking-[0.18em]",
          isToday ? "text-foreground" : "text-muted-foreground",
        )}
      >
        {abbr}
      </span>
      <span
        aria-hidden
        className={cn(
          "h-2 w-2 rounded-full transition-colors",
          filled ? "bg-primary" : "bg-muted",
          isToday && "ring-2 ring-primary/60 ring-offset-2 ring-offset-card",
        )}
      />
    </div>
  )
}

/**
 * Daily-streak placeholder for the Dashboard.
 *
 * Skeleton on purpose — the real "did you do today's tasks" logic
 * lands later. Today the card reserves the slot, sets the visual
 * vocabulary (week strip of 7 dots, today ring-highlighted, task
 * list below), and shows a clear "coming soon" hint so it can't be
 * mistaken for a finished feature.
 *
 * Compact rhythm (small header, condensed task list) so it fits the
 * single-viewport dashboard layout next to the verse + mini-calendar.
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
      className="animate-fade-in flex h-full flex-col overflow-hidden rounded-md border border-border bg-card"
    >
      <header className="flex items-center gap-2.5 border-b border-border bg-gradient-accent-subtle px-4 py-3 sm:px-5 sm:py-4">
        <Flame className="h-4 w-4 shrink-0 text-muted-foreground" strokeWidth={1.75} aria-hidden />
        <div className="min-w-0">
          <p className="text-[10px] font-medium uppercase tracking-[0.18em] text-muted-foreground">
            {t("streak.eyebrow")}
          </p>
          <h2
            id="streak-card-heading"
            className="font-serif text-sm font-semibold tracking-tight text-foreground"
          >
            {t("streak.title")}
          </h2>
        </div>
      </header>

      <div className="min-h-0 flex-1 space-y-3 overflow-y-auto px-4 py-3 sm:px-5 sm:py-4">
        <div role="group" aria-label={t("streak.weekAriaLabel")} className="flex items-end gap-1">
          {days.map((abbr, i) => (
            <DayCell key={i} abbr={abbr} filled={false} isToday={i === today} />
          ))}
        </div>

        <ul className="space-y-1.5">
          {tasks.map((label) => (
            <li key={label} className="flex items-center gap-2 text-xs text-muted-foreground">
              <span
                aria-hidden
                className="h-3 w-3 shrink-0 rounded-full border border-border bg-background"
              />
              <span className="truncate">{label}</span>
            </li>
          ))}
        </ul>
        <p className="inline-flex items-center gap-1.5 text-[11px] text-muted-foreground/80">
          <Sparkles
            className="h-3 w-3 shrink-0 text-muted-foreground/60"
            strokeWidth={1.75}
            aria-hidden
          />
          {t("streak.comingSoon")}
        </p>
      </div>
    </section>
  )
}
