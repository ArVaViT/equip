import type { ReactNode } from "react"
import { render, screen } from "@testing-library/react"
import { I18nextProvider } from "react-i18next"
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest"
import i18n from "@/i18n/config"
import { setDisplayTimeZone } from "@/i18n/timeZone"
import { SelectedDayPanel } from "../SelectedDayPanel"

function Wrapper({ children }: { children: ReactNode }) {
  return <I18nextProvider i18n={i18n}>{children}</I18nextProvider>
}

/**
 * The day panel's heading names the day that was clicked. The grid hands it
 * a local-midnight container for that day; formatting it in the profile's
 * zone moved it back a day whenever that zone is west of the browser's
 * (a laptop in Kyiv with Indianapolis chosen showed October 4 for a click
 * on October 5).
 */
describe("selected day heading", () => {
  beforeAll(async () => {
    await i18n.changeLanguage("en")
  })
  afterEach(() => setDisplayTimeZone(null))

  it("names the clicked day whatever zone the profile chose", () => {
    // Honolulu is west of every zone a test machine is likely to run in.
    setDisplayTimeZone("Pacific/Honolulu")
    render(<SelectedDayPanel selectedDay={new Date(2026, 9, 5)} events={[]} now={Date.now()} />, { wrapper: Wrapper })
    expect(screen.getByText("October 5")).toBeInTheDocument()
    expect(screen.getByText("Monday")).toBeInTheDocument()
  })

  const session = (date: string) =>
    ({
      id: "e", title: "Session", description: null, event_type: "live_session", event_date: date,
      meeting_url: "https://zoom.us/j/1", recording_url: "https://youtu.be/x", course_id: "c", course_title: null,
      source: "course_event",
    }) as never

  it("offers a past session's recording, not a way to join it or add it", () => {
    vi.useFakeTimers({ toFake: ["Date"] })
    vi.setSystemTime(new Date("2026-10-02T12:00:00Z"))
    render(<SelectedDayPanel selectedDay={new Date(2026, 8, 28)} events={[session("2026-09-28T18:00:00Z")]} now={Date.now()} />, {
      wrapper: Wrapper,
    })
    expect(screen.getByRole("link", { name: /Session/ })).toHaveAttribute("href", "https://youtu.be/x")
    expect(screen.queryByRole("button", { name: /calendar/i })).toBeNull()
    vi.useRealTimers()
  })

  it("still offers joining and adding a session that has not happened", () => {
    vi.useFakeTimers({ toFake: ["Date"] })
    vi.setSystemTime(new Date("2026-10-02T12:00:00Z"))
    render(<SelectedDayPanel selectedDay={new Date(2026, 9, 5)} events={[session("2026-10-05T18:00:00Z")]} now={Date.now()} />, {
      wrapper: Wrapper,
    })
    expect(screen.getByRole("link", { name: /zoom|join/i })).toHaveAttribute("href", "https://zoom.us/j/1")
    expect(screen.getByRole("button", { name: /calendar/i })).toBeInTheDocument()
    vi.useRealTimers()
  })
})
