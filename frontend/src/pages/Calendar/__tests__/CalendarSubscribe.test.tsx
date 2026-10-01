import type { ReactNode } from "react"
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { I18nextProvider } from "react-i18next"
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest"
import i18n from "@/i18n/config"

const issueIcalFeed = vi.fn()
vi.mock("@/services/calendar", () => ({ calendarService: { issueIcalFeed: () => issueIcalFeed() } }))
vi.mock("@/lib/toast", () => ({ toast: vi.fn() }))

import { CalendarSubscribe } from "../CalendarSubscribe"

function Wrapper({ children }: { children: ReactNode }) {
  return <I18nextProvider i18n={i18n}>{children}</I18nextProvider>
}

const FEED = "https://equipbible.com/api/v1/calendar/ical/feed?token=abc.def"

/**
 * The iCal feed existed with nothing in the interface pointing at it. Each
 * new link switches the previous one off, so the dialog must not create one
 * just by opening.
 */
describe("calendar subscription", () => {
  beforeAll(async () => {
    await i18n.changeLanguage("en")
  })
  beforeEach(() => {
    issueIcalFeed.mockReset()
    issueIcalFeed.mockResolvedValue({ feed_url: FEED, expires_at: "2027-09-30T00:00:00Z" })
  })

  it("does not create a link, and so break an old one, just by opening", async () => {
    const user = userEvent.setup()
    render(<CalendarSubscribe />, { wrapper: Wrapper })
    await user.click(screen.getByRole("button", { name: "Subscribe" }))
    expect(screen.getByText(/old link stops working/)).toBeInTheDocument()
    expect(issueIcalFeed).not.toHaveBeenCalled()
  })

  it("hands the link to Apple/Outlook as webcal and to Google as a cid", async () => {
    const user = userEvent.setup()
    render(<CalendarSubscribe />, { wrapper: Wrapper })
    await user.click(screen.getByRole("button", { name: "Subscribe" }))
    await user.click(screen.getByRole("button", { name: "Create link" }))
    await waitFor(() => expect(issueIcalFeed).toHaveBeenCalledTimes(1))

    expect(screen.getByRole("link", { name: "Apple and Outlook" })).toHaveAttribute(
      "href",
      "webcal://equipbible.com/api/v1/calendar/ical/feed?token=abc.def",
    )
    const google = screen.getByRole("link", { name: "Google Calendar" }).getAttribute("href")!
    expect(new URL(google).searchParams.get("cid")).toBe("webcal://equipbible.com/api/v1/calendar/ical/feed?token=abc.def")
  })
})
