import { fireEvent, render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { I18nextProvider } from "react-i18next"
import { afterEach, describe, expect, it, vi } from "vitest"

import i18n from "@/i18n/config"
import type { CalendarEvent } from "@/types"
import { AddToCalendarButton } from "../AddToCalendarButton"

const evt = {
  id: "e1",
  title: "Срок: эссе",
  description: null,
  event_type: "assignment_due",
  event_date: "2026-10-11T03:59:00Z",
  meeting_url: null,
  course_id: "c1",
  course_title: "Деяния",
  source: "assignment",
} as unknown as CalendarEvent

describe("AddToCalendarButton", () => {
  afterEach(() => vi.restoreAllMocks())

  it("offers Google and a calendar file, and stays inside its row", async () => {
    const create = vi.fn(() => "blob:x")
    Object.assign(URL, { createObjectURL: create, revokeObjectURL: vi.fn() })
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {})
    const rowClick = vi.fn()
    render(
      <I18nextProvider i18n={i18n}>
        <div onClick={rowClick}>
          <AddToCalendarButton event={evt} />
        </div>
      </I18nextProvider>,
    )
    await userEvent.click(screen.getByRole("button", { name: i18n.t("calendar.addOne.aria", { title: evt.title }) }))
    const google = await screen.findByRole("menuitem", { name: i18n.t("calendar.addOne.google") })
    expect(google).toHaveAttribute("href", expect.stringContaining("https://calendar.google.com/calendar/render?action=TEMPLATE"))
    expect(google).toHaveAttribute("target", "_blank")
    fireEvent.click(screen.getByRole("menuitem", { name: i18n.t("calendar.addOne.file") }))
    expect(create).toHaveBeenCalledOnce()
    const blob = (create.mock.calls[0] as unknown as [Blob])[0]
    expect(blob.type).toContain("text/calendar")
    expect(click).toHaveBeenCalledOnce()
    expect(rowClick).not.toHaveBeenCalled()
  })
})
