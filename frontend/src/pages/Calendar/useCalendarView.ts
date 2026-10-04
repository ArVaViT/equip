import { useCallback, useState } from "react";
import { useSearchParams } from "react-router-dom";

export type CalendarViewName = "agenda" | "week" | "month";

const STORAGE_KEY = "equip.calendar.view";

function isView(value: string | null): value is CalendarViewName {
  return value === "agenda" || value === "week" || value === "month";
}

function remembered(): CalendarViewName | null {
  try {
    const v = window.localStorage.getItem(STORAGE_KEY);
    return isView(v) ? v : null;
  } catch {
    return null;
  }
}

/**
 * Which view the page opens on: the link's `?view=`, then the reader's last
 * choice, then the screen — the list on a phone, where a month grid is
 * forty-two cells too small to read, the month on a desktop.
 */
export function useCalendarView(): [CalendarViewName, (v: CalendarViewName) => void] {
  const [params, setParams] = useSearchParams();
  const fromUrl = params.get("view");
  const [fallback] = useState<CalendarViewName>(() => {
    const stored = remembered();
    if (stored) return stored;
    const wide = typeof window !== "undefined" && window.matchMedia?.("(min-width: 1024px)").matches;
    return wide ? "month" : "agenda";
  });
  const view = isView(fromUrl) ? fromUrl : fallback;
  const setView = useCallback(
    (next: CalendarViewName) => {
      try {
        window.localStorage.setItem(STORAGE_KEY, next);
      } catch {
        // A private window: the choice lasts as long as the link does.
      }
      const p = new URLSearchParams(params);
      p.set("view", next);
      setParams(p, { replace: true });
    },
    [params, setParams],
  );
  return [view, setView];
}
