import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { BookOpen, CalendarDays, Clock } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/patterns";
import type { CalendarEvent } from "@/types";
import { getEventColor } from "./constants";
import { formatTime } from "./utils";
import { formatDateLong } from "@/i18n/format";

interface SelectedDayPanelProps {
  selectedDay: Date;
  events: CalendarEvent[];
}

export function SelectedDayPanel({ selectedDay, events }: SelectedDayPanelProps) {
  const { t } = useTranslation();
  const weekday = formatDateLong(selectedDay, {
    year: undefined,
    month: undefined,
    day: undefined,
    weekday: "long",
  });
  const dateLine = formatDateLong(selectedDay, {
    year: undefined,
    weekday: undefined,
    month: "long",
    day: "numeric",
  });
  return (
    <Card>
      <CardHeader className="pb-3">
        <p className="flex items-center gap-1.5 text-xs font-medium uppercase tracking-[0.18em] text-muted-foreground">
          <CalendarDays className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
          {weekday}
        </p>
        <CardTitle className="font-serif text-lg font-semibold tracking-tight">
          {dateLine}
        </CardTitle>
        {events.length > 0 && (
          <p className="text-xs text-muted-foreground tabular-nums">
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
            {events.map((evt) => {
              const color = getEventColor(evt.event_type);
              return (
                <div
                  key={evt.id}
                  className={`rounded-md border p-3 ${color.border} ${color.bg}`}
                >
                  <div className="flex items-start gap-2.5">
                    <span className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${color.dot}`} aria-hidden />
                    <div className="min-w-0 flex-1">
                      <p className={`text-sm font-medium text-wrap-safe ${color.text}`}>{evt.title}</p>
                      <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs text-muted-foreground">
                        <span className="flex items-center gap-1 tabular-nums">
                          <Clock className="h-3 w-3" strokeWidth={1.75} aria-hidden />
                          {formatTime(evt.event_date)}
                        </span>
                        <span aria-hidden className="text-muted-foreground/40">·</span>
                        <span>{t(`calendar.eventTypes.${evt.event_type}`, { defaultValue: evt.event_type.replace("_", " ") })}</span>
                      </div>
                      {evt.course_title && (
                        <Link
                          to={`/courses/${evt.course_id}`}
                          className="mt-1.5 inline-flex items-center gap-1 text-xs text-primary underline-offset-4 hover:underline"
                        >
                          <BookOpen className="h-3 w-3" strokeWidth={1.75} aria-hidden />
                          {evt.course_title}
                        </Link>
                      )}
                      {evt.description && (
                        <p className="mt-1.5 text-xs text-muted-foreground line-clamp-3">
                          {evt.description}
                        </p>
                      )}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
