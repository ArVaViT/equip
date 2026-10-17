/**
 * A certificate is dated on its school's day, for every reader.
 *
 * Signed at 23:30 in Indianapolis on October 24 (03:30 UTC on the 25th), it
 * used to read «25 October» in Kyiv and on Kiritimati. The server now sends
 * `issued_on`, and every surface prints that day as it is — no zone applied,
 * so it does not slip a day west of Greenwich either.
 */
import { render, screen } from "@testing-library/react"
import { I18nextProvider } from "react-i18next"
import { MemoryRouter } from "react-router-dom"
import { afterEach, describe, expect, it, vi } from "vitest"

import i18n from "@/i18n/config"
import { documentDay, formatDayLong } from "@/i18n/format"
import { setDisplayTimeZone } from "@/i18n/timeZone"
import { coursesService } from "@/services/courses"
import type { Certificate } from "@/types"
import TranscriptPage from "../TranscriptPage"

vi.mock("@/context/useAuth", () => ({ useAuth: () => ({ user: { full_name: "Anna" } }) }))

const LATE_IN_INDIANA = "2026-10-25T03:30:00Z"
const READERS = ["Europe/Kyiv", "America/Los_Angeles", "Pacific/Kiritimati", "America/Indiana/Indianapolis"]

describe("the day a document is dated", () => {
  afterEach(async () => {
    setDisplayTimeZone(null)
    vi.restoreAllMocks()
    await i18n.changeLanguage("en")
  })

  it("is the school's day whatever the reader's zone", () => {
    for (const zone of READERS) {
      setDisplayTimeZone(zone)
      expect(documentDay("2026-10-24", LATE_IN_INDIANA)).toBe("2026-10-24")
      expect(formatDayLong("2026-10-24", undefined, "en-GB")).toBe("24 October 2026")
    }
  })

  it("prints in the interface's language when no locale is given, without a zone", async () => {
    await i18n.changeLanguage("ru")
    expect(formatDayLong("2026-10-24")).toMatch(/^24 октября 2026/)
    expect(formatDayLong("2026-01-01", { month: "short" })).toMatch(/^1 янв/)
    expect(formatDayLong(null)).toBe("")
    expect(formatDayLong("24.10.2026")).toBe("")
  })

  it("falls back to the reader's day for a response from an older server", () => {
    setDisplayTimeZone("Europe/Kyiv")
    expect(documentDay(undefined, LATE_IN_INDIANA)).toBe("2026-10-25")
    setDisplayTimeZone("America/Indiana/Indianapolis")
    expect(documentDay(null, LATE_IN_INDIANA)).toBe("2026-10-24")
    expect(documentDay(null, null)).toBeNull()
  })

  it("puts the school's day on the transcript for a reader in Kyiv", async () => {
    setDisplayTimeZone("Europe/Kyiv")
    vi.spyOn(coursesService, "getMyCertificates").mockResolvedValue([
      {
        id: "c1",
        status: "approved",
        student_name: "Anna Petrenko",
        school_name: null,
        certificate_number: "EQ-1",
        course_title: "Acts",
        issued_at: LATE_IN_INDIANA,
        issued_on: "2026-10-24",
      } as Certificate,
    ])
    render(
      <I18nextProvider i18n={i18n}>
        <MemoryRouter>
          <TranscriptPage />
        </MemoryRouter>
      </I18nextProvider>,
    )
    expect(await screen.findByRole("heading", { name: "Anna Petrenko" })).toBeInTheDocument()
    const row = screen.getAllByRole("row")[1]
    expect(row?.textContent).toContain("24 October 2026")
    expect(row?.textContent).not.toContain("25 October")
  })
})
