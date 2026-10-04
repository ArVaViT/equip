import { useEffect, useRef } from "react"

import { usePrefersReducedMotion } from "@/hooks/usePrefersReducedMotion"
import { calendarDayKey } from "./utils"

/** Below Tailwind's `lg`: the day panel sits under the grid, not beside it. */
const NARROW = "(max-width: 1023px)"

function isNarrow(): boolean {
  return typeof window !== "undefined" && typeof window.matchMedia === "function" && window.matchMedia(NARROW).matches
}

/**
 * On a phone, tapping a day in the month or the week put the day's cards
 * below the fold — the grid is taller than the screen, and nothing moved.
 * The tap looked like it had done nothing.
 *
 * So after a tap that changes the day, the panel is scrolled to on narrow
 * screens. Only after a tap: the first render, «Today», and the month and
 * week arrows also change the day, and a page that scrolls itself on
 * opening is a page that jumps. Wide screens keep the panel in view beside
 * the grid and are left alone.
 */
export function useScrollToSelectedDay(selectedDay: Date | null, select: (day: Date) => void) {
  const panelRef = useRef<HTMLDivElement>(null)
  const tapped = useRef(false)
  const reducedMotion = usePrefersReducedMotion()
  const key = selectedDay ? calendarDayKey(selectedDay) : null

  const selectByTap = (day: Date) => {
    // Tapping the day already open changes nothing, and must not leave
    // a flag behind for the next arrow press to trip over.
    if (calendarDayKey(day) !== key) tapped.current = true
    select(day)
  }

  useEffect(() => {
    if (!tapped.current) return
    tapped.current = false
    if (!isNarrow()) return
    const el = panelRef.current
    // jsdom has no `scrollIntoView`; a browser always does.
    if (!el || typeof el.scrollIntoView !== "function") return
    el.scrollIntoView({ behavior: reducedMotion ? "auto" : "smooth", block: "start" })
  }, [key, reducedMotion])

  return { panelRef, selectByTap }
}
