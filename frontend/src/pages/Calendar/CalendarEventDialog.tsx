import { useEffect, useId, useState } from "react";
import { useTranslation } from "react-i18next";

import type { Course } from "@/types";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useConfirm } from "@/components/ui/alert-dialog";
import { EventsModal } from "@/pages/Teacher/editor/EventsModal";
import { useEventsSection } from "@/pages/Teacher/editor/useEventsSection";

/**
 * The course editor's events dialog, opened from the calendar: a teacher
 * looking at next week should not have to leave it, find the course, open
 * the editor and find the button to put a class on Saturday. The same form,
 * the same series and scope rules — with the course picked here.
 */
export function CalendarEventDialog({
  open,
  courses,
  initialCourseId,
  onClose,
}: {
  open: boolean;
  courses: Course[];
  initialCourseId?: string;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const confirm = useConfirm();
  const pickerId = useId();
  const firstOwned = courses.find((c) => c.id === initialCourseId)?.id ?? courses[0]?.id;
  const [courseId, setCourseId] = useState<string | undefined>(firstOwned);
  useEffect(() => {
    if (open) setCourseId(firstOwned);
  }, [open, firstOwned]);
  const section = useEventsSection(open ? courseId : undefined, confirm);

  return (
    <EventsModal
      open={open}
      onClose={() => {
        section.resetForm();
        onClose();
      }}
      header={
        courses.length > 1 ? (
          <div className="space-y-1">
            <Label htmlFor={pickerId} className="text-xs">
              {t("calendar.newEvent.course")}
            </Label>
            <Select
              value={courseId}
              onValueChange={(v) => {
                section.resetForm();
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
