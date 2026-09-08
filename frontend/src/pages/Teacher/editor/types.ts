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
}

export const EMPTY_EVENT_FORM: EventFormState = {
  title: "",
  description: "",
  event_type: "other",
  event_date: "",
  meeting_url: "",
}

export type CourseEditorModal =
  | "enroll"
  | "announce"
  | "materials"
  | "events"
  | "access"
  | null
