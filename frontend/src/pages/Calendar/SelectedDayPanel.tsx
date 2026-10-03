import { useTranslation } from "react-i18next";
import { CalendarDays } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/patterns";
import type { CalendarEvent } from "@/types";
import { EventCard } from "@/components/calendar/EventCard";
import { formatCalendarDay } from "@/i18n/format";

interface SelectedDayPanelProps {
  selectedDay: Date;
  events: CalendarEvent[];
  now: number;
  compact?: boolean;
}

export function SelectedDayPanel({ selectedDay, events, now, compact = false }: SelectedDayPanelProps) {
  const { t } = useTranslation();
  const weekday = formatCalendarDay(selectedDay, {
    year: undefined,
    month: undefined,
    day: undefined,
    weekday: "long",
  });
  const dateLine = formatCalendarDay(selectedDay, {
    year: undefined,
    weekday: undefined,
    month: "long",
    day: "numeric",
  });
  return (
    <Card>
      <CardHeader className="pb-3">
        <p className="flex items-center gap-1.5 text-xs font-medium uppercase tracking-[0.18em] text-ink-muted">
          <CalendarDays className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
          {weekday}
        </p>
        <CardTitle>
          {dateLine}
        </CardTitle>
        {events.length > 0 && (
          <p className="text-xs text-ink-muted tabular-nums">
            {t("calendar.eventCount", { count: events.length })}
          </p>
        )}
      </CardHeader>
      <CardContent>
        {events.length === 0 ? (
          <EmptyState
            variant="compact"
            icon={<CalendarDays strokeWidth={1.75} aria-hidden />}
            title={t("calendar.selectedDayEmpty")}
          />
        ) : (
          <div className="space-y-2">
            {events.map((evt) => (
              <EventCard key={evt.id} event={evt} now={now} compact={compact} />
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
