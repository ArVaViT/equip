export interface MaterialFile {
  name: string
  path: string
  size?: number
}

export interface EventFormState {
  title: string
  description: string
  event_type: string
  event_date: string
  /** Empty string, not `null`: this is the value of a controlled
   *  `<input>`, and the blank is what "no meeting" looks like in a form.
   *  It is turned into an absent field on the way to the server. */
  meeting_url: string
  /** The recording's address, added after the session. Blank = none. */
  recording_url: string
  /** Minutes as typed in a `<select>`; blank = no length (a deadline). */
  duration_minutes: string
  /** "0" = once; "1" = every week; "2" = every other week. New events only. */
  repeat_every: "0" | "1" | "2"
  /** How many classes the series holds, the first one included. */
  repeat_count: string
}

/** The lengths offered for a class. An exam can take a morning. */
export const DURATION_CHOICES = [30, 45, 60, 75, 90, 120, 150, 180, 240] as const

/** Mirrors ``MAX_OCCURRENCES`` in ``backend/app/services/event_series.py``. */
export const MAX_SERIES = 52

/** A kind that happens over a span of time, and so has a length. */
export function takesTime(eventType: string): boolean {
  return eventType !== "deadline"
}

export const EMPTY_EVENT_FORM: EventFormState = {
  title: "",
  description: "",
  event_type: "other",
  event_date: "",
  meeting_url: "",
  recording_url: "",
  duration_minutes: "",
  repeat_every: "0",
  repeat_count: "8",
}

export type CourseEditorModal =
  | "enroll"
  | "announce"
  | "materials"
  | "events"
  | "access"
  | null
