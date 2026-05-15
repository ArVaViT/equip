import { useTranslation } from "react-i18next";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { ChevronLeft, ChevronRight } from "lucide-react";

import type { CalendarEvent } from "@/types";
import { DAY_NAMES, EVENT_COLORS, MONTH_NAMES, getEventColor } from "./constants";
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
  const { t } = useTranslation();
  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="font-serif text-lg">
            {MONTH_NAMES[month]} {year}
          </CardTitle>
          <div className="flex items-center gap-1">
            <Button
              variant="ghost"
              size="sm"
              className="h-8 w-8 p-0"
              onClick={onPrevMonth}
              aria-label={t("calendar.prevMonth")}
            >
              <ChevronLeft className="h-4 w-4" strokeWidth={1.75} />
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
              <ChevronRight className="h-4 w-4" strokeWidth={1.75} />
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent className="pt-2">
        <div className="grid grid-cols-7 mb-1">
          {DAY_NAMES.map((d) => (
            <div
              key={d}
              className="text-center text-xs font-medium text-muted-foreground uppercase tracking-wider py-1"
            >
              {d}
            </div>
          ))}
        </div>

        <div className="grid grid-cols-7 border-t border-l">
          {calendarDays.map(({ date, inMonth }) => {
            const key = calendarDayKey(date);
            const dayEvents = eventsByDate.get(key) ?? [];
            const isToday = isSameDay(date, today);
            const isSelected = selectedDay != null && isSameDay(date, selectedDay);

            return (
              <button
                key={key}
                onClick={() => onSelectDay(date)}
                className={`
                  relative min-h-[72px] sm:min-h-[80px] p-1 border-r border-b text-left transition-colors
                  ${inMonth ? "bg-background" : "bg-muted/30"}
                  ${isSelected ? "ring-2 ring-primary ring-inset" : "hover:bg-muted/50"}
                `}
              >
                <span
                  className={`
                    inline-flex items-center justify-center w-6 h-6 text-xs font-medium rounded-full
                    ${isToday ? "bg-primary text-primary-foreground" : ""}
                    ${!inMonth ? "text-muted-foreground/40" : ""}
                  `}
                >
                  {date.getDate()}
                </span>

                {dayEvents.length > 0 && (
                  <div className="flex flex-wrap gap-0.5 mt-0.5">
                    {dayEvents.slice(0, 3).map((evt) => {
                      const color = getEventColor(evt.event_type);
                      return (
                        <span
                          key={evt.id}
                          className={`block w-full rounded px-1 py-0.5 text-xs leading-tight truncate ${color.bg} ${color.text}`}
                          title={evt.title}
                        >
                          {evt.title}
                        </span>
                      );
                    })}
                    {dayEvents.length > 3 && (
                      <span className="text-xs text-muted-foreground pl-1">
                        {t("calendar.moreEvents", { count: dayEvents.length - 3 })}
                      </span>
                    )}
                  </div>
                )}
              </button>
            );
          })}
        </div>

        <div className="flex flex-wrap items-center gap-3 mt-3 text-xs">
          {Object.entries(EVENT_COLORS).map(([type, color]) => (
            <span key={type} className="flex items-center gap-1">
              <span className={`w-2 h-2 rounded-full ${color.dot}`} />
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
