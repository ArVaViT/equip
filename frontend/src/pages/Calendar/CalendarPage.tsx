import { getDisplayTimeZone, timeZoneOptionLabel, zonedToday } from "@/i18n/timeZone";
import { activeIntlTag } from "@/i18n/config";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { CalendarDays, CalendarPlus, Filter, RefreshCw } from "lucide-react";
import { useState } from "react";

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
import { CalendarEventDialog } from "./CalendarEventDialog";
import { CalendarEditingContext, type CalendarEditing } from "@/components/calendar/calendarEditing";
import { usePrompt } from "@/components/ui/alert-dialog";
import { coursesService } from "@/services/courses";
import { getErrorDetail } from "@/lib/errorDetail";
import { toast } from "@/lib/toast";
import type { CalendarEvent } from "@/types";
import { SelectedDayPanel } from "./SelectedDayPanel";
import { useCalendarData } from "./useCalendarData";
import { useMonthGrid } from "./useMonthGrid";
import { useScrollToSelectedDay } from "./useScrollToSelectedDay";

export default function CalendarPage() {
  const { t, i18n } = useTranslation();
  const {
    events,
    enrollments,
    teaching,
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
  const { panelRef, selectByTap } = useScrollToSelectedDay(selectedDay, setSelectedDay);
  const [creating, setCreating] = useState(false);
  const prompt = usePrompt();
  const teachingIds = new Set(teaching.map((c) => c.id));
  const editing: CalendarEditing | null =
    teaching.length === 0
      ? null
      : {
          canEdit: (e: CalendarEvent) => e.source === "course_event" && teachingIds.has(e.course_id),
          addRecording: (e: CalendarEvent) => {
            void (async () => {
              const url = await prompt({
                title: t("calendar.card.addRecordingTitle", { title: e.title }),
                description: t("meeting.recordingHint"),
                placeholder: t("meeting.recordingPlaceholder"),
                inputType: "url",
                confirmLabel: t("calendar.card.addRecordingSave"),
              });
              if (!url?.trim()) return;
              try {
                await coursesService.updateCourseEvent(e.course_id, e.id, { recording_url: url.trim() });
                toast({ title: t("calendar.card.recordingAdded"), variant: "success" });
                retry();
              } catch (err) {
                toast({ title: getErrorDetail(err, t("teacherEditor.toast.eventSaveFailed")), variant: "destructive" });
              }
            })();
          },
        };
  const now = useNow();

  useUserTour({
    tourId: "calendar-v1",
    steps: calendarSteps(t),
    ready: !loading && !fetchError && (enrollments.length > 0 || teaching.length > 0),
  });

  // Only the first load blanks the page. A refresh after the teacher adds
  // a class keeps what is on screen until the new list arrives.
  if (loading && events.length === 0 && enrollments.length === 0 && teaching.length === 0) {
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
  const hasNoEnrollments = enrollments.length === 0 && teaching.length === 0 && events.length === 0;
  // The filter lists what the reader studies and what they teach: a
  // teacher's own courses are on this calendar too, and were missing
  // from the one control that narrows it.
  const filterCourses = [
    ...enrollments.map((e) => ({ id: e.course_id, title: e.course?.title ?? e.course_id })),
    ...teaching
      .filter((c) => !enrollments.some((e) => e.course_id === c.id))
      .map((c) => ({ id: c.id, title: c.title })),
  ];

  return (
    <CalendarEditingContext.Provider value={editing}>
      <div className="container mx-auto px-4 py-8 max-w-6xl">
        <div className="mb-8 flex flex-col items-start justify-between gap-4 sm:flex-row sm:items-end">
          <div>
            <p className="mb-2 text-xs font-medium uppercase tracking-[0.18em] text-ink-muted">
              {t("calendar.eyebrow")}
            </p>
            <h1 className="font-serif text-3xl font-semibold tracking-tight sm:text-4xl">
              {t("calendar.title")}
            </h1>
            {/* Whose 20:00: a school in Indiana teaches people in Kyiv. */}
            <p className="mt-2 text-sm text-ink-muted">
              {t("calendar.zone", {
                zone: timeZoneOptionLabel(activeIntlTag(i18n.resolvedLanguage ?? i18n.language), getDisplayTimeZone()),
              })}{" "}
              <Link to="/profile#time-zone" className="text-ink underline underline-offset-4 hover:text-brand">
                {t("calendar.zoneChange")}
              </Link>
            </p>
          </div>

          {filterCourses.length > 0 && (
            <div className="flex flex-wrap items-center gap-2">
              {teaching.length > 0 && (
                <Button size="sm" onClick={() => setCreating(true)}>
                  <CalendarPlus className="mr-1.5 h-4 w-4" strokeWidth={1.75} aria-hidden />
                  {t("calendar.newEvent.open")}
                </Button>
              )}
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
                    {filterCourses.map((c) => (
                      <SelectItem key={c.id} value={c.id}>
                        {c.title}
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
                  onSelectDay={selectByTap}
                  onPrevWeek={prevWeek}
                  onNextWeek={nextWeek}
                  onGoToday={goToday}
                />
                {selectedDay && (
                  <div ref={panelRef} className="mx-auto max-w-3xl scroll-mt-20">
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
                    onSelectDay={selectByTap}
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
                    <div ref={panelRef} className="scroll-mt-20">
                      <SelectedDayPanel selectedDay={selectedDay} events={selectedDayEvents} now={now} compact />
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        )}
        {teaching.length > 0 && (
          <CalendarEventDialog
            open={creating}
            courses={teaching}
            events={events}
            initialCourseId={filterCourseId || undefined}
            onClose={() => {
              setCreating(false);
              // What was just scheduled belongs on the page now.
              retry();
            }}
          />
        )}
      </div>
    </CalendarEditingContext.Provider>
  );
}
