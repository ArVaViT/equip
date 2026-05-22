// Shared event-type constants extracted from badges.tsx so consumers can
// import the i18n key map without dragging the React component module
// (which trips the react-refresh/only-export-components lint rule when
// the .tsx file exports both components and constants).

export const EVENT_TYPE_LABEL_KEYS = {
  deadline: "teacherEditor.modals.events.types.deadline",
  live_session: "teacherEditor.modals.events.types.live_session",
  exam: "teacherEditor.modals.events.types.exam",
  other: "teacherEditor.modals.events.types.other",
} as const

export type EventType = keyof typeof EVENT_TYPE_LABEL_KEYS
