import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { BookOpen, CalendarDays, Clock } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { CalendarEvent } from "@/types";
import { getEventColor } from "./constants";
import { formatTime } from "./utils";
import { formatDate } from "@/i18n/format";

interface SelectedDayPanelProps {
  selectedDay: Date;
  events: CalendarEvent[];
}

export function SelectedDayPanel({ selectedDay, events }: SelectedDayPanelProps) {
  const { t } = useTranslation();
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium flex items-center gap-2">
          <CalendarDays className="h-4 w-4 text-primary" />
          {formatDate(selectedDay, {
            weekday: "long",
            month: "long",
            day: "numeric",
          })}
        </CardTitle>
      </CardHeader>
      <CardContent>
        {events.length === 0 ? (
          <p className="text-sm text-muted-foreground py-3 text-center">
            {t("calendar.selectedDayEmpty")}
          </p>
        ) : (
          <div className="space-y-2">
            {events.map((evt) => {
              const color = getEventColor(evt.event_type);
              return (
                <div
                  key={evt.id}
                  className={`rounded-lg border p-2.5 ${color.border} ${color.bg}`}
                >
                  <div className="flex items-start gap-2">
                    <span className={`mt-1 w-2 h-2 rounded-full shrink-0 ${color.dot}`} />
                    <div className="flex-1 min-w-0">
                      <p className={`text-sm font-medium ${color.text}`}>{evt.title}</p>
                      <div className="flex items-center gap-2 mt-0.5 text-[10px] text-muted-foreground">
                        <span className="flex items-center gap-0.5">
                          <Clock className="h-2.5 w-2.5" />
                          {formatTime(evt.event_date)}
                        </span>
                        <span>{t(`calendar.eventTypes.${evt.event_type}`, { defaultValue: evt.event_type.replace("_", " ") })}</span>
                      </div>
                      {evt.course_title && (
                        <Link
                          to={`/courses/${evt.course_id}`}
                          className="flex items-center gap-1 mt-1 text-[10px] text-primary hover:underline"
                        >
                          <BookOpen className="h-2.5 w-2.5" />
                          {evt.course_title}
                        </Link>
                      )}
                      {evt.description && (
                        <p className="text-[10px] text-muted-foreground mt-1 line-clamp-2">
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
