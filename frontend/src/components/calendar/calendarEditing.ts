import { createContext, useContext } from "react"
import type { CalendarEvent } from "@/types"

/**
 * What a teacher can do to an event from wherever it is shown. Provided by
 * the calendar page for the courses the reader teaches; absent everywhere
 * else, so a student's card never grows a teacher's button.
 */
export interface CalendarEditing {
  canEdit: (event: CalendarEvent) => boolean
  addRecording: (event: CalendarEvent) => void
}

export const CalendarEditingContext = createContext<CalendarEditing | null>(null)

export function useCalendarEditing(): CalendarEditing | null {
  return useContext(CalendarEditingContext)
}
