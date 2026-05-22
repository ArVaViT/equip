import { Clock } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/patterns";
import type { CalendarEvent } from "@/types";
import { getEventColor } from "./constants";
import { formatShortDate, formatTime, isOverdue } from "./utils";

interface UpcomingEventsPanelProps {
  events: CalendarEvent[];
}

/**
 * Sidebar list of events happening in the next 14 days. Past deadlines
 * get flagged as overdue so the student can act on them.
 */
export function UpcomingEventsPanel({ events }: UpcomingEventsPanelProps) {
  const { t } = useTranslation();
  return (
    <Card>
      <CardHeader className="pb-3">
        <p className="text-xs font-medium uppercase tracking-[0.18em] text-muted-foreground">
          {t("calendar.upcomingEyebrow")}
        </p>
        <CardTitle className="font-serif text-lg font-semibold tracking-tight">
          {t("calendar.upcomingTitle")}
        </CardTitle>
      </CardHeader>
      <CardContent>
        {events.length === 0 ? (
          <EmptyState
            variant="compact"
            icon={<Clock strokeWidth={1.75} aria-hidden />}
            title={t("calendar.upcomingEmpty")}
          />
        ) : (
          <div className="space-y-2">
            {events.map((evt) => {
              const color = getEventColor(evt.event_type);
              const overdue = evt.event_type === "deadline" && isOverdue(evt.event_date);
              return (
                <div
                  key={evt.id}
                  className={`flex items-start gap-2.5 rounded-md border p-2.5 transition-colors ${
                    overdue
                      ? "border-destructive/30 bg-destructive/5"
                      : "border-border hover:bg-muted/40"
                  }`}
                >
                  <span className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${color.dot}`} aria-hidden />
                  <div className="min-w-0 flex-1">
                    <p
                      className={`truncate text-sm font-medium ${
                        overdue ? "text-destructive" : ""
                      }`}
                    >
                      {evt.title}
                    </p>
                    <div className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs text-muted-foreground tabular-nums">
                      <span>{formatShortDate(evt.event_date)}</span>
                      <span aria-hidden className="text-muted-foreground/40">·</span>
                      <span>{formatTime(evt.event_date)}</span>
                      {overdue && (
                        <span className="rounded bg-destructive/10 px-1.5 py-0.5 font-medium text-destructive">
                          {t("calendar.overdue")}
                        </span>
                      )}
                    </div>
                    {evt.course_title && (
                      <p className="mt-0.5 truncate text-xs text-muted-foreground/70">
                        {evt.course_title}
                      </p>
                    )}
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
