import { zonedCalendarDate, zonedToday } from "@/i18n/timeZone";
import { useMemo, useState } from "react";

import type { CalendarEvent } from "@/types";
import { addDays, startOfWeekMon, weekdayMonStart } from "@/lib/calendar";
import { calendarDayKey } from "./utils";

interface DayCell {
  date: Date;
  inMonth: boolean;
}

/**
 * Derives everything the calendar views need: the Monday-start grid of the
 * visible month, the seven days of the visible week, a `Map` of events keyed
 * by day in the reader's zone, and the selected day's events.
 *
 * One anchor drives both the month and the week: moving a week across a
 * month boundary moves the month with it, so switching views never lands
 * the reader somewhere else in time.
 */
export function useMonthGrid(events: CalendarEvent[]) {
  // Today on the reader's calendar (profile zone), not the browser's.
  const [currentDate, setCurrentDate] = useState(() => zonedToday());
  const [selectedDay, setSelectedDay] = useState<Date | null>(() => zonedToday());

  const year = currentDate.getFullYear();
  const month = currentDate.getMonth();

  const calendarDays = useMemo<DayCell[]>(() => {
    const firstDay = new Date(year, month, 1);
    const lastDay = new Date(year, month + 1, 0);
    const startOffset = weekdayMonStart(firstDay);
    const days: DayCell[] = [];

    for (let i = startOffset - 1; i >= 0; i--) {
      days.push({ date: new Date(year, month, -i), inMonth: false });
    }
    for (let i = 1; i <= lastDay.getDate(); i++) {
      days.push({ date: new Date(year, month, i), inMonth: true });
    }
    const remaining = 7 - (days.length % 7);
    if (remaining < 7) {
      for (let i = 1; i <= remaining; i++) {
        days.push({ date: new Date(year, month + 1, i), inMonth: false });
      }
    }
    return days;
  }, [year, month]);

  const weekStart = startOfWeekMon(selectedDay ?? currentDate);
  const weekStartKey = calendarDayKey(weekStart);
  const weekDays = useMemo(
    () => Array.from({ length: 7 }, (_, i) => addDays(weekStart, i)),
    // eslint-disable-next-line react-hooks/exhaustive-deps -- keyed by the day, not the Date object
    [weekStartKey],
  );

  const eventsByDate = useMemo(() => {
    const map = new Map<string, CalendarEvent[]>();
    for (const evt of events) {
      if (!evt.event_date) continue;
      const d = new Date(evt.event_date);
      if (Number.isNaN(d.getTime())) continue;
      // The day the event falls on in the reader's zone.
      const key = calendarDayKey(zonedCalendarDate(d));
      const bucket = map.get(key);
      if (bucket) bucket.push(evt);
      else map.set(key, [evt]);
    }
    for (const bucket of map.values()) bucket.sort((a, b) => a.event_date.localeCompare(b.event_date));
    return map;
  }, [events]);

  const selectedDayEvents = useMemo(() => {
    if (!selectedDay) return [];
    return eventsByDate.get(calendarDayKey(selectedDay)) ?? [];
  }, [selectedDay, eventsByDate]);

  const goTo = (day: Date) => {
    setCurrentDate(new Date(day.getFullYear(), day.getMonth(), 1));
    setSelectedDay(day);
  };

  return {
    year,
    month,
    calendarDays,
    weekDays,
    eventsByDate,
    selectedDay,
    // Picking a day in the month's leading or trailing week moves the
    // month there too, so the grid and the day panel never disagree.
    setSelectedDay: (day: Date) => goTo(day),
    selectedDayEvents,
    // ``selectedDay`` follows the visible month -- otherwise navigating
    // May -> June while May-15 was selected leaves the side panel claiming
    // "events for May 15" under an empty June grid. Anchor it to the 1st of
    // the destination month; ``goToday`` snaps both back to today.
    prevMonth: () => goTo(new Date(year, month - 1, 1)),
    nextMonth: () => goTo(new Date(year, month + 1, 1)),
    prevWeek: () => goTo(addDays(weekStart, -7)),
    nextWeek: () => goTo(addDays(weekStart, 7)),
    goToday: () => goTo(zonedToday()),
  };
}
