import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { CalendarDays, Filter, RefreshCw } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import PageSpinner from "@/components/ui/PageSpinner";
import { EmptyState, ErrorState } from "@/components/patterns";

import { MonthGrid } from "./MonthGrid";
import { SelectedDayPanel } from "./SelectedDayPanel";
import { UpcomingEventsPanel } from "./UpcomingEventsPanel";
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
    eventsByDate,
    selectedDay,
    setSelectedDay,
    selectedDayEvents,
    upcomingEvents,
    prevMonth,
    nextMonth,
    goToday,
  } = useMonthGrid(events);

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
          <p className="mb-2 text-xs font-medium uppercase tracking-[0.18em] text-muted-foreground">
            {t("calendar.eyebrow")}
          </p>
          <h1 className="font-serif text-3xl font-semibold tracking-tight sm:text-4xl">
            {t("calendar.title")}
          </h1>
        </div>

        {enrollments.length > 0 && (
          <div className="flex items-center gap-2">
            <Filter className="h-3.5 w-3.5 text-muted-foreground" strokeWidth={1.75} aria-hidden />
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
        )}
      </div>

      {hasNoEnrollments ? (
        <EmptyState
          icon={<CalendarDays strokeWidth={1.75} aria-hidden />}
          title={t("calendar.noEnrollmentsTitle")}
          description={t("calendar.noEnrollmentsDescription")}
          action={
            // ``/courses`` (the catalog) since the home/courses split in
            // PR #381; ``/`` is now the Dashboard, which is empty for a
            // user with no enrollments and would just bounce them right
            // back here.
            <Link to="/courses">
              <Button size="sm">{t("calendar.browseCourses")}</Button>
            </Link>
          }
        />
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2">
            <MonthGrid
              year={year}
              month={month}
              today={new Date()}
              calendarDays={calendarDays}
              eventsByDate={eventsByDate}
              selectedDay={selectedDay}
              onSelectDay={setSelectedDay}
              onPrevMonth={prevMonth}
              onNextMonth={nextMonth}
              onGoToday={goToday}
            />
          </div>

          <div className="space-y-4">
            {selectedDay && (
              <SelectedDayPanel selectedDay={selectedDay} events={selectedDayEvents} />
            )}
            <UpcomingEventsPanel events={upcomingEvents} />
          </div>
        </div>
      )}
    </div>
  );
}
