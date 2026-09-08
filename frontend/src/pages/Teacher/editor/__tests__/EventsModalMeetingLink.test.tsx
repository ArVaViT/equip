import React from "react"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { I18nextProvider } from "react-i18next"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import i18n from "@/i18n/config"
import { EventsModal } from "../EventsModal"
import { EMPTY_EVENT_FORM, type EventFormState } from "../types"
import type { CourseEvent } from "@/types"

/**
 * The teacher's end of the meeting link.
 *
 * The field is optional and has to look optional: a deadline and an
 * exam in a room have nothing to join, and those are most events. But
 * a link that has been typed and is not a link must stop the save
 * there and then — the alternative is a toast after the round trip,
 * about a field she has already stopped looking at.
 */

const ZOOM = "https://zoom.us/j/1234567890?pwd=aB3dEf"

function Wrapper({ children }: { children: React.ReactNode }) {
  return <I18nextProvider i18n={i18n}>{children}</I18nextProvider>
}

function renderModal(form: Partial<EventFormState> = {}, events: CourseEvent[] = []) {
  const onSave = vi.fn()
  const onFormChange = vi.fn()
  render(
    <EventsModal
      open
      onClose={vi.fn()}
      events={events}
      form={{ ...EMPTY_EVENT_FORM, title: "Занятие", event_date: "2026-10-03T18:00", ...form }}
      onFormChange={onFormChange}
      editingId={null}
      saving={false}
      onSave={onSave}
      onCancelEdit={vi.fn()}
      onEdit={vi.fn()}
      onDelete={vi.fn()}
    />,
    { wrapper: Wrapper },
  )
  return { onSave, onFormChange }
}

function saveButton() {
  return screen.getByRole("button", { name: /Создать событие/ })
}

describe("EventsModal — the meeting link", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru")
  })
  afterEach(async () => {
    await i18n.changeLanguage("en")
  })

  it("offers the field with a hint naming the tools a teacher actually uses", () => {
    renderModal()
    expect(screen.getByLabelText("Ссылка на встречу")).toBeInTheDocument()
    expect(screen.getByText(/Zoom, Google Meet/)).toBeInTheDocument()
  })

  it("does not make an event wait for a link it does not need", () => {
    // Empty is the ordinary case, and it saves.
    renderModal({ meeting_url: "" })
    expect(saveButton()).toBeEnabled()
  })

  it("blocks the save and says why when the link is not a web address", async () => {
    const user = userEvent.setup()
    const { onSave } = renderModal({ meeting_url: "javascript:alert(1)" })
    expect(saveButton()).toBeDisabled()
    expect(screen.getByRole("alert")).toHaveTextContent(
      /должна начинаться с http:\/\/ или https:\/\//,
    )
    await user.click(saveButton())
    expect(onSave).not.toHaveBeenCalled()
  })

  it("blocks a scheme-less host, which is the commonest way to get this wrong", () => {
    renderModal({ meeting_url: "zoom.us/j/1234567890" })
    expect(saveButton()).toBeDisabled()
    expect(screen.getByRole("alert")).toBeInTheDocument()
  })

  it("marks the field itself as the one at fault", () => {
    renderModal({ meeting_url: "не ссылка" })
    expect(screen.getByLabelText("Ссылка на встречу")).toHaveAttribute("aria-invalid", "true")
  })

  it("lets a real link through", () => {
    renderModal({ meeting_url: ZOOM })
    expect(saveButton()).toBeEnabled()
    expect(screen.queryByRole("alert")).toBeNull()
    // The hint is back once the field is valid again.
    expect(screen.getByText(/Zoom, Google Meet/)).toBeInTheDocument()
  })

  it("shows the teacher the same join button her students will see", () => {
    renderModal({}, [
      {
        id: "evt-1",
        course_id: "c1",
        title: "Занятие по проповеди",
        description: null,
        event_type: "live_session",
        event_date: "2026-10-03T18:00:00Z",
        meeting_url: ZOOM,
        created_by: "u1",
        created_at: "2026-09-07T10:00:00Z",
      },
    ])
    // How she finds out before Saturday that the link opens the room
    // she meant.
    expect(screen.getByRole("link", { name: /Присоединиться/ })).toHaveAttribute("href", ZOOM)
  })
})
