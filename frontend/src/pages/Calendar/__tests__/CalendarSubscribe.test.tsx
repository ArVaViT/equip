import type { ReactNode } from "react"
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { I18nextProvider } from "react-i18next"
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest"
import i18n from "@/i18n/config"

const issueIcalFeed = vi.fn()
vi.mock("@/services/calendar", () => ({ calendarService: { issueIcalFeed: () => issueIcalFeed() } }))
vi.mock("@/lib/toast", () => ({ toast: vi.fn() }))

import { CalendarSubscribe } from "../CalendarSubscribe"
import { calendarPlatform } from "../calendarPlatform"

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

    expect(screen.getByRole("link", { name: "Apple Calendar, Outlook" })).toHaveAttribute(
      "href",
      "webcal://equipbible.com/api/v1/calendar/ical/feed?token=abc.def",
    )
    const google = screen.getByRole("link", { name: "Google Calendar" }).getAttribute("href")!
    expect(new URL(google).searchParams.get("cid")).toBe("webcal://equipbible.com/api/v1/calendar/ical/feed?token=abc.def")
    // Google refreshes a subscription every few hours: a moved class shows
    // there late, and the student is told so before they rely on it.
    expect(screen.getByText(/Google checks every few hours/)).toBeInTheDocument()
  })

  describe("puts the calendar this device keeps first", () => {
    const ANDROID = "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 Chrome/128.0 Mobile Safari/537.36"
    const IPHONE = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 Version/17.5 Mobile/15E148 Safari/604.1"
    const WINDOWS = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128.0 Safari/537.36"

    afterEach(() => vi.restoreAllMocks())

    it.each([
      [ANDROID, "android"],
      [IPHONE, "apple"],
      ["Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 Version/17.5 Safari/605.1.15", "apple"],
      [WINDOWS, "other"],
      ["", "other"],
    ])("reads %s as %s", (ua, platform) => {
      expect(calendarPlatform(ua)).toBe(platform)
    })

    async function linksAfterCreate(userAgent: string) {
      vi.spyOn(navigator, "userAgent", "get").mockReturnValue(userAgent)
      const user = userEvent.setup()
      render(<CalendarSubscribe />, { wrapper: Wrapper })
      await user.click(screen.getByRole("button", { name: "Subscribe" }))
      await user.click(screen.getByRole("button", { name: "Create link" }))
      await waitFor(() => expect(issueIcalFeed).toHaveBeenCalledTimes(1))
      return screen.getAllByRole("link").map((a) => ({ name: a.textContent, solid: a.className.includes("bg-brand ") }))
    }

    it("on Android, Google Calendar comes first and solid", async () => {
      const links = await linksAfterCreate(ANDROID)
      expect(links.map((l) => l.name)).toEqual(["Google Calendar", "Apple Calendar, Outlook"])
      expect(links.map((l) => l.solid)).toEqual([true, false])
    })

    it("on an iPhone, the Apple link stays first and solid", async () => {
      const links = await linksAfterCreate(IPHONE)
      expect(links.map((l) => l.name)).toEqual(["Apple Calendar, Outlook", "Google Calendar"])
      expect(links.map((l) => l.solid)).toEqual([true, false])
    })

    it("anywhere else keeps the order it had", async () => {
      const links = await linksAfterCreate(WINDOWS)
      expect(links.map((l) => l.name)).toEqual(["Apple Calendar, Outlook", "Google Calendar"])
    })
  })
})
