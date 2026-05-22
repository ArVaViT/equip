import { useMemo, useState } from "react";

import type { CalendarEvent } from "@/types";
import { calendarDayKey } from "./utils";

interface DayCell {
  date: Date;
  inMonth: boolean;
}

/**
 * Derives everything the calendar UI needs to render a month at a time:
 * the Sunday-padded grid of day cells, a `Map` of events keyed by day,
 * the events for the currently-selected day, and the next 14 days of
 * upcoming events.
 *
 * Everything is memoised so re-rendering on selection doesn't rebuild
 * the grid or the bucket.
 */
export function useMonthGrid(events: CalendarEvent[]) {
  const [currentDate, setCurrentDate] = useState(() => new Date());
  const [selectedDay, setSelectedDay] = useState<Date | null>(() => new Date());

  const year = currentDate.getFullYear();
  const month = currentDate.getMonth();

  const calendarDays = useMemo<DayCell[]>(() => {
    const firstDay = new Date(year, month, 1);
    const lastDay = new Date(year, month + 1, 0);
    const startOffset = firstDay.getDay();
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

  const eventsByDate = useMemo(() => {
    const map = new Map<string, CalendarEvent[]>();
    for (const evt of events) {
      if (!evt.event_date) continue;
      const d = new Date(evt.event_date);
      if (Number.isNaN(d.getTime())) continue;
      const key = calendarDayKey(d);
      const bucket = map.get(key);
      if (bucket) bucket.push(evt);
      else map.set(key, [evt]);
    }
    return map;
  }, [events]);

  const selectedDayEvents = useMemo(() => {
    if (!selectedDay) return [];
    return eventsByDate.get(calendarDayKey(selectedDay)) ?? [];
  }, [selectedDay, eventsByDate]);

  const upcomingEvents = useMemo(() => {
    const now = new Date();
    const twoWeeks = new Date(now.getTime() + 14 * 24 * 60 * 60 * 1000);
    return events.filter((e) => {
      if (!e.event_date) return false;
      const d = new Date(e.event_date);
      if (Number.isNaN(d.getTime())) return false;
      return d >= now && d <= twoWeeks;
    });
  }, [events]);

  return {
    year,
    month,
    calendarDays,
    eventsByDate,
    selectedDay,
    setSelectedDay,
    selectedDayEvents,
    upcomingEvents,
    // ``selectedDay`` needs to follow the visible month -- otherwise
    // navigating May -> June while May-15 was selected leaves the
    // right-side panel claiming "events for May 15" while rendering
    // an empty June grid. Anchor selectedDay to the 1st of the
    // destination month so the panel reads the new month's data on
    // navigation; ``goToday`` snaps both the grid AND selection back
    // to today.
    prevMonth: () => {
      const nextMonthStart = new Date(year, month - 1, 1)
      setCurrentDate(nextMonthStart)
      setSelectedDay(nextMonthStart)
    },
    nextMonth: () => {
      const nextMonthStart = new Date(year, month + 1, 1)
      setCurrentDate(nextMonthStart)
      setSelectedDay(nextMonthStart)
    },
    goToday: () => {
      const today = new Date()
      setCurrentDate(today)
      setSelectedDay(today)
    },
  };
}
