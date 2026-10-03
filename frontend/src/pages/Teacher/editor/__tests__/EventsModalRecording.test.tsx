import React from "react"
import { render, screen } from "@testing-library/react"
import { I18nextProvider } from "react-i18next"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import i18n from "@/i18n/config"
import { EventsModal } from "../EventsModal"
import { EMPTY_EVENT_FORM, type EventFormState } from "../types"

/** A recording belongs to a live session that has happened: the field is there and nowhere else. */

function Wrapper({ children }: { children: React.ReactNode }) {
  return <I18nextProvider i18n={i18n}>{children}</I18nextProvider>
}

function renderEditing(form: Partial<EventFormState>, editingId: string | null = "e1") {
  render(
    <EventsModal
      open
      onClose={vi.fn()}
      events={[]}
      form={{ ...EMPTY_EVENT_FORM, title: "Занятие", event_date: "2026-10-03T18:00", ...form }}
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

describe("EventsModal — the recording link", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru")
  })
  afterEach(async () => {
    await i18n.changeLanguage("en")
  })

  it("is offered on a live session being edited", () => {
    renderEditing({ event_type: "live_session" })
    expect(screen.getByLabelText("Ссылка на запись")).toBeInTheDocument()
  })

  it("is not offered on a deadline", () => {
    renderEditing({ event_type: "deadline" })
    expect(screen.queryByLabelText("Ссылка на запись")).toBeNull()
  })

  it("is not offered on a new live session", () => {
    renderEditing({ event_type: "live_session" }, null)
    expect(screen.queryByLabelText("Ссылка на запись")).toBeNull()
  })

  it("stays where a link was already added, so it can be taken off", () => {
    renderEditing({ event_type: "deadline", recording_url: "https://youtu.be/x" })
    expect(screen.getByLabelText("Ссылка на запись")).toHaveValue("https://youtu.be/x")
  })
})
