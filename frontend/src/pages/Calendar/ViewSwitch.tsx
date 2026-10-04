import { useTranslation } from "react-i18next";
import { CalendarDays, CalendarRange, ListChecks } from "lucide-react";

import { cn } from "@/lib/utils";

import type { CalendarViewName } from "./useCalendarView";

const VIEWS: { value: CalendarViewName; icon: typeof ListChecks }[] = [
  { value: "agenda", icon: ListChecks },
  { value: "week", icon: CalendarRange },
  { value: "month", icon: CalendarDays },
];

export function ViewSwitch({ value, onChange }: { value: CalendarViewName; onChange: (v: CalendarViewName) => void }) {
  const { t } = useTranslation();
  return (
    <div role="group" aria-label={t("calendar.views.label")} className="inline-flex rounded-md border border-edge bg-muted/30 p-0.5">
      {VIEWS.map(({ value: v, icon: Icon }) => (
        <button
          key={v}
          type="button"
          aria-pressed={value === v}
          onClick={() => onChange(v)}
          className={cn(
            "inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand",
            value === v ? "bg-surface text-ink shadow-sm" : "text-ink-muted hover:text-ink",
          )}
        >
          <Icon className="h-4 w-4" strokeWidth={1.75} aria-hidden />
          {t(`calendar.views.${v}`)}
        </button>
      ))}
    </div>
  );
}
