import React from "react"
import { render, screen } from "@testing-library/react"
import { I18nextProvider } from "react-i18next"
import { afterEach, beforeEach, describe, expect, it } from "vitest"

import i18n from "@/i18n/config"
import { JoinMeetingLink } from "../JoinMeetingLink"

/**
 * The way into a live session, as a thing you press.
 *
 * Two properties matter more than the styling. An event with no meeting
 * — which is most of them — must render nothing at all, because an
 * empty button that goes nowhere is a promise the row cannot keep. And
 * a link that is not an `http(s)` address must never reach the `href`:
 * React puts whatever it is given there, and a `javascript:` value runs
 * in the reader's session the moment they click something labelled
 * «Присоединиться».
 */

const ZOOM = "https://zoom.us/j/1234567890?pwd=aB3dEf"

function Wrapper({ children }: { children: React.ReactNode }) {
  return <I18nextProvider i18n={i18n}>{children}</I18nextProvider>
}

describe("JoinMeetingLink", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru")
  })
  afterEach(async () => {
    await i18n.changeLanguage("en")
  })

  it("reads as an action rather than as an address", () => {
    render(<JoinMeetingLink url={ZOOM} title="Занятие по проповеди" />, { wrapper: Wrapper })
    const link = screen.getByRole("link")
    // The label is the verb. The URL itself is never printed — on a
    // phone a bare address had to be copied character by character.
    expect(link).toHaveTextContent("Присоединиться")
    expect(link.textContent).not.toContain("zoom.us")
    expect(link).toHaveAttribute("href", ZOOM)
  })

  it("opens beside the lesson and hands the opened page no way back", () => {
    render(<JoinMeetingLink url={ZOOM} title="Занятие" />, { wrapper: Wrapper })
    const link = screen.getByRole("link")
    expect(link).toHaveAttribute("target", "_blank")
    expect(link).toHaveAttribute("rel", "noopener noreferrer")
  })

  it("names the event it belongs to, because a list holds several", () => {
    render(<JoinMeetingLink url={ZOOM} title="Занятие по проповеди" />, { wrapper: Wrapper })
    expect(screen.getByRole("link")).toHaveAccessibleName(
      "Присоединиться к встрече — Занятие по проповеди",
    )
  })

  it.each([null, undefined, "", "   "])("renders nothing when there is no meeting (%s)", (url) => {
    const { container } = render(<JoinMeetingLink url={url} title="Дедлайн" />, { wrapper: Wrapper })
    expect(screen.queryByRole("link")).toBeNull()
    expect(container).toBeEmptyDOMElement()
  })

  it.each([
    "javascript:alert(document.cookie)",
    "JavaScript:alert(1)",
    "data:text/html,<script>alert(1)</script>",
    "/calendar",
    "zoom.us/j/1",
    "https://zoom.us@evil.example.com/j/1",
  ])("refuses to put %s in an href even if the API returned it", (url) => {
    // The server already refuses these on the way in, so reaching this
    // branch means that check has regressed. The button is the last
    // thing between a stored payload and the student's click.
    render(<JoinMeetingLink url={url} title="Занятие" />, { wrapper: Wrapper })
    expect(screen.queryByRole("link")).toBeNull()
  })

  it("speaks the reader's language", async () => {
    await i18n.changeLanguage("de")
    render(<JoinMeetingLink url={ZOOM} title="Predigtstunde" />, { wrapper: Wrapper })
    expect(screen.getByRole("link")).toHaveTextContent("Beitreten")
  })
})
