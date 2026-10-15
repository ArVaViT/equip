import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { I18nextProvider } from "react-i18next"
import { describe, expect, it } from "vitest"

import i18n from "@/i18n/config"
import type { CalendarEvent } from "@/types"
import { CourseRecordings } from "../CourseRecordings"

const ev = (id: string, date: string, recording: string | null): CalendarEvent =>
  ({ id, title: `Урок ${id}`, description: null, event_type: "live_session", event_date: date, meeting_url: null,
     recording_url: recording, course_id: "c", course_title: null, source: "course_event" }) as CalendarEvent

const wrap = (events: CalendarEvent[]) =>
  render(<I18nextProvider i18n={i18n}><CourseRecordings events={events} /></I18nextProvider>)

describe("CourseRecordings", () => {
  it("is absent until a class has a recording", () => {
    const { container } = wrap([ev("1", "2026-09-12T00:00:00Z", null)])
    expect(container).toBeEmptyDOMElement()
  })

  it("lists the recorded classes newest first, three before 'all'", async () => {
    wrap([
      ev("1", "2026-09-05T00:00:00Z", "https://youtu.be/1"),
      ev("2", "2026-09-12T00:00:00Z", "https://youtu.be/2"),
      ev("3", "2026-09-19T00:00:00Z", "https://youtu.be/3"),
      ev("4", "2026-09-26T00:00:00Z", "https://youtu.be/4"),
      ev("5", "2026-10-03T00:00:00Z", null),
    ])
    const items = () => screen.getAllByRole("listitem").map((li) => li.textContent ?? "")
    expect(items()).toHaveLength(3)
    expect(items()[0]).toContain("Урок 4")
    await userEvent.click(screen.getByRole("button", { expanded: false }))
    expect(items()).toHaveLength(4)
    expect(items()[3]).toContain("Урок 1")
  })
})
