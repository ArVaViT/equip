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
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium flex items-center gap-2">
          <Clock className="h-4 w-4 text-muted-foreground" />
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
                  className={`flex items-start gap-2 rounded-md border p-2 transition-colors ${
                    overdue
                      ? "border-destructive/30 bg-destructive/5"
                      : "hover:bg-muted/50"
                  }`}
                >
                  <span className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${color.dot}`} />
                  <div className="min-w-0 flex-1">
                    <p
                      className={`truncate text-xs font-medium ${
                        overdue ? "text-destructive" : ""
                      }`}
                    >
                      {evt.title}
                    </p>
                    <div className="mt-0.5 flex items-center gap-2 text-[10px] text-muted-foreground">
                      <span>{formatShortDate(evt.event_date)}</span>
                      <span>{formatTime(evt.event_date)}</span>
                      {overdue && (
                        <span className="font-medium text-destructive">{t("calendar.overdue")}</span>
                      )}
                    </div>
                    {evt.course_title && (
                      <p className="text-[10px] text-muted-foreground/70 truncate mt-0.5">
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
