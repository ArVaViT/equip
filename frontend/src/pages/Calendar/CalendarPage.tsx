import { zonedToday } from "@/i18n/timeZone";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { CalendarDays, Filter, RefreshCw } from "lucide-react";

import { Button } from "@/components/ui/button";
import { CalendarSubscribe } from "./CalendarSubscribe";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import PageSpinner from "@/components/ui/PageSpinner";
import { EmptyState, ErrorState } from "@/components/patterns";
import { useUserTour } from "@/hooks/useUserTour";
import { calendarSteps } from "@/lib/tourSteps";

import { useNow } from "@/hooks/useNow";
import { AgendaView } from "./AgendaView";
import { MonthGrid } from "./MonthGrid";
import { NextUpCard } from "./NextUpCard";
import { ViewSwitch } from "./ViewSwitch";
import { useCalendarView } from "./useCalendarView";
import { WeekView } from "./WeekView";
import { SelectedDayPanel } from "./SelectedDayPanel";
import { useCalendarData } from "./useCalendarData";
import { useMonthGrid } from "./useMonthGrid";

export default function CalendarPage() {
  const { t } = useTranslation();
  const {
    events,
    enrollments,
    loading,
    fetchError,
    retry,
    filterCourseId,
    setFilterCourseId,
  } = useCalendarData();

  const {
    year,
    month,
    calendarDays,
    weekDays,
    eventsByDate,
    selectedDay,
    setSelectedDay,
    selectedDayEvents,
    prevMonth,
    nextMonth,
    prevWeek,
    nextWeek,
    goToday,
  } = useMonthGrid(events);
  const [view, setView] = useCalendarView();
  const now = useNow();

  useUserTour({
    tourId: "calendar-v1",
    steps: calendarSteps(t),
    ready: !loading && !fetchError && enrollments.length > 0,
  });

  if (loading) {
    return <PageSpinner />;
  }

  if (fetchError) {
    return (
      <div className="container mx-auto px-4">
        <ErrorState
          description={fetchError}
          action={
            <Button variant="outline" size="sm" onClick={retry}>
              <RefreshCw className="h-3.5 w-3.5 mr-1.5" strokeWidth={1.75} />
              {t("calendar.retry")}
            </Button>
          }
        />
      </div>
    );
  }

  // A student with no enrollments cannot have calendar events. Skip the
  // empty month grid + empty sidebar (two "no events" blocks stacked) and
  // show a single page-level empty state that points to the courses
  // catalog — same pattern as HomePage's noEnrollments empty state.
  const hasNoEnrollments = enrollments.length === 0 && events.length === 0;

  return (
    <div className="container mx-auto px-4 py-8 max-w-6xl">
      <div className="mb-8 flex flex-col items-start justify-between gap-4 sm:flex-row sm:items-end">
        <div>
          <p className="mb-2 text-xs font-medium uppercase tracking-[0.18em] text-ink-muted">
            {t("calendar.eyebrow")}
          </p>
          <h1 className="font-serif text-3xl font-semibold tracking-tight sm:text-4xl">
            {t("calendar.title")}
          </h1>
        </div>

        {enrollments.length > 0 && (
          <div className="flex flex-wrap items-center gap-2">
            <CalendarSubscribe />
            <div className="flex items-center gap-2">
              <Filter className="h-3.5 w-3.5 text-ink-muted" strokeWidth={1.75} aria-hidden />
              <Select
                value={filterCourseId || "all"}
                onValueChange={(v) => setFilterCourseId(v === "all" ? "" : v)}
              >
                <SelectTrigger
                  size="md"
                  className="max-w-xs min-w-[12rem]"
                  aria-label={t("calendar.filterByCourse")}
                >
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">{t("calendar.allCourses")}</SelectItem>
                  {enrollments.map((e) => (
                    <SelectItem key={e.course_id} value={e.course_id}>
                      {e.course?.title ?? e.course_id}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
        )}
      </div>

      {hasNoEnrollments ? (
        <EmptyState
          icon={<CalendarDays strokeWidth={1.75} aria-hidden />}
          title={t("calendar.noEnrollmentsTitle")}
          description={t("calendar.noEnrollmentsDescription")}
          action={
            // ``/`` is the Dashboard (empty for a user with no
            // enrollments and would bounce them back here), so route
            // them to the catalog instead.
            <Link to="/courses">
              <Button size="sm">{t("calendar.browseCourses")}</Button>
            </Link>
          }
        />
      ) : (
        <div className="space-y-6">
          <ViewSwitch value={view} onChange={setView} />
          {view === "agenda" && (
            // No "next class" card here: the list is already "what is next",
            // and the card would repeat its first entry.
            <div data-tour="calendar-upcoming" className="mx-auto max-w-3xl space-y-6">
              <AgendaView events={events} now={now} />
            </div>
          )}
          {view === "week" && (
            <div data-tour="calendar-grid" className="space-y-6">
              <NextUpCard events={events} now={now} hideOnDay={selectedDay} />
              <WeekView
                weekDays={weekDays}
                eventsByDate={eventsByDate}
                today={zonedToday()}
                selectedDay={selectedDay}
                now={now}
                onSelectDay={setSelectedDay}
                onPrevWeek={prevWeek}
                onNextWeek={nextWeek}
                onGoToday={goToday}
              />
              {selectedDay && (
                <div className="mx-auto max-w-3xl">
                  <SelectedDayPanel selectedDay={selectedDay} events={selectedDayEvents} now={now} />
                </div>
              )}
            </div>
          )}
          {view === "month" && (
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              <div data-tour="calendar-grid" className="lg:col-span-2">
                <MonthGrid
                  year={year}
                  month={month}
                  today={zonedToday()}
                  calendarDays={calendarDays}
                  eventsByDate={eventsByDate}
                  selectedDay={selectedDay}
                  onSelectDay={setSelectedDay}
                  onPrevMonth={prevMonth}
                  onNextMonth={nextMonth}
                  onGoToday={goToday}
                />
              </div>

              {/* Beside the month: the day the reader opened, and the next
                  class when it is on another day. The full list of what is
                  ahead is the "Schedule" view, not a third copy here. */}
              <div data-tour="calendar-upcoming" className="space-y-4">
                <NextUpCard events={events} now={now} hideOnDay={selectedDay} compact />
                {selectedDay && (
                  <SelectedDayPanel selectedDay={selectedDay} events={selectedDayEvents} now={now} compact />
                )}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
