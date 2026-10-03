import React from "react"
import { render, screen } from "@testing-library/react"
import { I18nextProvider } from "react-i18next"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import i18n from "@/i18n/config"
import { setDisplayTimeZone } from "@/i18n/timeZone"
import { EventsModal } from "../EventsModal"
import { EMPTY_EVENT_FORM, type EventFormState } from "../types"
import type { CourseEvent } from "@/types"

/** A class has a length and can repeat; a deadline has neither. */

function Wrapper({ children }: { children: React.ReactNode }) {
  return <I18nextProvider i18n={i18n}>{children}</I18nextProvider>
}

function renderForm(form: Partial<EventFormState>, editingId: string | null = null, events: CourseEvent[] = []) {
  render(
    <EventsModal
      open
      onClose={vi.fn()}
      events={events}
      form={{ ...EMPTY_EVENT_FORM, title: "Урок", event_date: "2026-10-24T20:00", ...form }}
      onFormChange={vi.fn()}
      editingId={editingId}
      saving={false}
      onSave={vi.fn()}
      onCancelEdit={vi.fn()}
      onEdit={vi.fn()}
      onDelete={vi.fn()}
    />,
    { wrapper: Wrapper },
  )
}

describe("EventsModal — length and repetition", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru")
    setDisplayTimeZone("America/Indiana/Indianapolis")
  })
  afterEach(async () => {
    await i18n.changeLanguage("en")
    setDisplayTimeZone(null)
  })

  it("offers a length and a repeat for a new class", () => {
    renderForm({ event_type: "live_session" })
    expect(screen.getByLabelText("Длительность")).toBeInTheDocument()
    expect(screen.getByLabelText("Повторять")).toBeInTheDocument()
  })

  it("offers neither for a deadline", () => {
    renderForm({ event_type: "deadline" })
    expect(screen.queryByLabelText("Длительность")).toBeNull()
    expect(screen.queryByLabelText("Повторять")).toBeNull()
  })

  it("does not offer to repeat an event being edited", () => {
    renderForm({ event_type: "live_session" }, "e1")
    expect(screen.getByLabelText("Длительность")).toBeInTheDocument()
    expect(screen.queryByLabelText("Повторять")).toBeNull()
  })

  it("names the last class of a weekly series", () => {
    renderForm({ event_type: "live_session", repeat_every: "1", repeat_count: "8" })
    expect(screen.getByLabelText("Всего занятий")).toHaveValue(8)
    // Oct 24 + 7 weeks = Dec 12.
    expect(screen.getByText(/последнее — 12 декабря 2026/)).toBeInTheDocument()
  })

  it("refuses a series of more than a year and blocks the save", () => {
    renderForm({ event_type: "live_session", repeat_every: "1", repeat_count: "60" })
    expect(screen.getByText("От 2 до 52")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: /Создать/ })).toBeDisabled()
  })

  it("numbers each lesson of a series in the list", () => {
    const lesson = (id: string, index: number): CourseEvent => ({
      id, course_id: "c1", title: "Урок", description: null, event_type: "live_session",
      event_date: `2026-10-${10 + 7 * (index - 1)}T20:00:00Z`, meeting_url: null, recording_url: null,
      duration_minutes: 90, series_id: "s1", series_index: index, series_count: 3,
      created_by: "t", created_at: "2026-10-01T00:00:00Z",
    })
    renderForm({ event_type: "live_session" }, null, [lesson("a", 1), lesson("b", 2), lesson("c", 3)])
    expect(screen.getByText("1 из 3")).toBeInTheDocument()
    expect(screen.getByText("2 из 3")).toBeInTheDocument()
    expect(screen.getByText("3 из 3")).toBeInTheDocument()
  })
})
