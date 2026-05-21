import { useTranslation } from "react-i18next";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { ChevronLeft, ChevronRight } from "lucide-react";

import type { CalendarEvent } from "@/types";
import { EVENT_COLORS, getDayShortName, getEventColor, getMonthName } from "./constants";
import { calendarDayKey, isSameDay } from "./utils";

interface MonthGridProps {
  year: number;
  month: number;
  today: Date;
  calendarDays: Array<{ date: Date; inMonth: boolean }>;
  eventsByDate: Map<string, CalendarEvent[]>;
  selectedDay: Date | null;
  onSelectDay: (date: Date) => void;
  onPrevMonth: () => void;
  onNextMonth: () => void;
  onGoToday: () => void;
}

/**
 * Calendar grid with month navigation and legend. All events come in
 * pre-bucketed by day via `eventsByDate` so this component stays pure.
 */
export function MonthGrid({
  year,
  month,
  today,
  calendarDays,
  eventsByDate,
  selectedDay,
  onSelectDay,
  onPrevMonth,
  onNextMonth,
  onGoToday,
}: MonthGridProps) {
  const { t, i18n } = useTranslation();
  const locale = i18n.resolvedLanguage ?? i18n.language ?? "en";
  // ``getMonthName`` / ``getDayShortName`` are locale-aware via Intl;
  // previously this file read hard-coded English ``MONTH_NAMES`` /
  // ``DAY_NAMES`` arrays, so the calendar grid rendered "January Sun
  // Mon Tue" regardless of the user's language.
  const dayLabels = Array.from({ length: 7 }, (_, i) => getDayShortName(i, locale));
  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between gap-3">
          <div>
            <p className="text-[11px] font-medium uppercase tracking-[0.18em] text-muted-foreground tabular-nums">
              {year}
            </p>
            <CardTitle className="font-serif text-lg font-semibold tracking-tight">
              {getMonthName(month, locale)}
            </CardTitle>
          </div>
          <div className="flex items-center gap-1">
            <Button
              variant="ghost"
              size="sm"
              className="h-8 w-8 p-0"
              onClick={onPrevMonth}
              aria-label={t("calendar.prevMonth")}
            >
              <ChevronLeft className="h-4 w-4" strokeWidth={1.75} aria-hidden />
            </Button>
            <Button variant="outline" size="sm" className="h-8 text-xs" onClick={onGoToday}>
              {t("calendar.today")}
            </Button>
            <Button
              variant="ghost"
              size="sm"
              className="h-8 w-8 p-0"
              onClick={onNextMonth}
              aria-label={t("calendar.nextMonth")}
            >
              <ChevronRight className="h-4 w-4" strokeWidth={1.75} aria-hidden />
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent className="pt-2">
        <div className="mb-1 grid grid-cols-7">
          {dayLabels.map((d, i) => {
            const isWeekend = i === 0 || i === 6;
            return (
              <div
                key={i}
                className={`py-1.5 text-center text-[11px] font-medium uppercase tracking-[0.18em] ${
                  isWeekend ? "text-muted-foreground/60" : "text-muted-foreground"
                }`}
              >
                {d}
              </div>
            );
          })}
        </div>

        <div className="grid grid-cols-7 border-l border-t border-border">
          {calendarDays.map(({ date, inMonth }) => {
            const key = calendarDayKey(date);
            const dayEvents = eventsByDate.get(key) ?? [];
            const isToday = isSameDay(date, today);
            const isSelected = selectedDay != null && isSameDay(date, selectedDay);
            const dayIndex = date.getDay();
            const isWeekend = dayIndex === 0 || dayIndex === 6;

            return (
              <button
                key={key}
                onClick={() => onSelectDay(date)}
                aria-pressed={isSelected}
                className={`
                  relative min-h-[78px] border-b border-r border-border p-1.5 text-left transition-colors sm:min-h-[88px]
                  ${inMonth ? (isWeekend ? "bg-muted/15" : "bg-background") : "bg-muted/30"}
                  ${isSelected ? "ring-2 ring-primary ring-inset" : "hover:bg-muted/40"}
                `}
              >
                <span
                  className={`
                    inline-flex h-6 w-6 items-center justify-center rounded-full text-xs font-medium tabular-nums
                    ${isToday ? "bg-primary text-primary-foreground" : ""}
                    ${!inMonth ? "text-muted-foreground/40" : ""}
                  `}
                >
                  {date.getDate()}
                </span>

                {dayEvents.length > 0 && (
                  <div className="mt-1 flex flex-wrap gap-0.5">
                    {dayEvents.slice(0, 3).map((evt) => {
                      const color = getEventColor(evt.event_type);
                      return (
                        <span
                          key={evt.id}
                          className={`block w-full truncate rounded px-1 py-0.5 text-xs leading-tight ${color.bg} ${color.text}`}
                          title={evt.title}
                        >
                          {evt.title}
                        </span>
                      );
                    })}
                    {dayEvents.length > 3 && (
                      <span className="pl-1 text-xs text-muted-foreground">
                        {t("calendar.moreEvents", { count: dayEvents.length - 3 })}
                      </span>
                    )}
                  </div>
                )}
              </button>
            );
          })}
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-1.5 text-xs">
          {Object.entries(EVENT_COLORS).map(([type, color]) => (
            <span key={type} className="flex items-center gap-1.5">
              <span className={`h-2 w-2 shrink-0 rounded-full ${color.dot}`} aria-hidden />
              <span className="text-muted-foreground">
                {t(`calendar.eventTypes.${type}`, { defaultValue: type.replace("_", " ") })}
              </span>
            </span>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
