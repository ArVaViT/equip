import { useEffect, useId, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import type { CalendarEvent, Course } from "@/types";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useConfirm } from "@/components/ui/alert-dialog";
import { useNow } from "@/hooks/useNow";
import { EventsModal } from "@/pages/Teacher/editor/EventsModal";
import { useEventsSection } from "@/pages/Teacher/editor/useEventsSection";
import { courseOfRecentLiveSession, newEventDefaults } from "./newEventDefaults";

/**
 * The course editor's events dialog, opened from the calendar: a teacher
 * looking at next week should not have to leave it, find the course, open
 * the editor and find the button to put a class on Saturday. The same form,
 * the same series and scope rules — with the course picked here, and the
 * form started from the course's last class (see `newEventDefaults`).
 */
export function CalendarEventDialog({
  open,
  courses,
  events,
  initialCourseId,
  onClose,
}: {
  open: boolean;
  courses: Course[];
  /** What the calendar already holds: the course's last class is read off it. */
  events: CalendarEvent[];
  initialCourseId?: string;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const confirm = useConfirm();
  const pickerId = useId();
  const now = useNow();
  // The course the calendar is filtered to; else the one the teacher last
  // held a class on; else the first they teach.
  const teachingIds = useMemo(() => new Set(courses.map((c) => c.id)), [courses]);
  const firstOwned =
    courses.find((c) => c.id === initialCourseId)?.id ??
    courseOfRecentLiveSession(events, teachingIds, now) ??
    courses[0]?.id;
  const [courseId, setCourseId] = useState<string | undefined>(firstOwned);
  useEffect(() => {
    if (open) setCourseId(firstOwned);
  }, [open, firstOwned]);
  const defaults = useMemo(() => newEventDefaults(events, courseId, now), [events, courseId, now]);
  const section = useEventsSection(open ? courseId : undefined, confirm, defaults.form);
  // A blank form each time the dialog opens. A course picked inside it, or
  // a calendar that loads late, only refills the fields nobody has typed
  // in (useEventsSection) — a title already written survives the switch.
  const { resetForm } = section;
  useEffect(() => {
    if (open) resetForm();
  }, [open, resetForm]);

  return (
    <EventsModal
      open={open}
      onClose={() => {
        section.resetForm();
        onClose();
      }}
      defaultTime={defaults.defaultTime}
      header={
        courses.length > 1 ? (
          <div className="space-y-1">
            <Label htmlFor={pickerId} className="text-xs">
              {t("calendar.newEvent.course")}
            </Label>
            <Select
              value={courseId}
              onValueChange={(v) => {
                // An event open for editing belongs to the course left behind.
                if (section.editingId) section.resetForm();
                setCourseId(v);
              }}
            >
              <SelectTrigger id={pickerId} size="sm">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {courses.map((c) => (
                  <SelectItem key={c.id} value={c.id}>
                    {c.title}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        ) : null
      }
      events={section.events}
      form={section.form}
      onFormChange={section.setForm}
      editingId={section.editingId}
      saving={section.saving}
      onSave={section.save}
      onCancelEdit={section.resetForm}
      onEdit={section.startEdit}
      onDelete={section.remove}
      pendingScope={section.pendingScope}
      onChooseScope={section.chooseScope}
      onCancelScope={section.cancelScope}
    />
  );
}
