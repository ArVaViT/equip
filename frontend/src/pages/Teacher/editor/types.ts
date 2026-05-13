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
}

export const EMPTY_EVENT_FORM: EventFormState = {
  title: "",
  description: "",
  event_type: "other",
  event_date: "",
}

export type CourseEditorModal =
  | "enroll"
  | "announce"
  | "materials"
  | "events"
  | null
