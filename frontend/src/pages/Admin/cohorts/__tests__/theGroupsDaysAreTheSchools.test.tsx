/**
 * A group's days are the school's, for every reader.
 *
 * A поток starting at 23:30 on October 31 in Indianapolis (03:30 UTC on
 * November 1) read «2026-11-01» in Kyiv — on the cohorts tab, on the cohort's
 * own page and on the course page a student enrols from. The server now sends
 * `start_on` and friends on the school's clock, and every surface prints that
 * day as it is; the certificate and the ведомость already did (2026-10-17).
 */
import { render, screen } from "@testing-library/react"
import { I18nextProvider } from "react-i18next"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import i18n from "@/i18n/config"
import { formatDay } from "@/i18n/format"
import { setDisplayTimeZone } from "@/i18n/timeZone"
import { NotEnrolledView } from "@/pages/Course/detail/NotEnrolledView"
import { cohortsService } from "@/services/cohorts"
import type { Cohort, Course } from "@/types"

vi.mock("@/lib/toast", () => ({ toast: vi.fn() }))
vi.mock("@/components/ui/alert-dialog", () => ({ useConfirm: () => async () => true }))
vi.mock("@/context/useAuth", () => ({
  useAuth: () => ({ user: { id: "d1", role: "director", email: "d@example.com" }, loading: false }),
}))

import CohortDetailPage from "../CohortDetailPage"

// 23:30 EDT on Saturday October 31 — already Sunday the 1st in UTC and in Kyiv.
const LATE_ON_THE_31ST = "2026-11-01T03:30:00Z"
// Indiana's clocks went back on November 1. The same 04:30 UTC that was 00:30
// on the Saturday before is 23:30 EST on Monday the 2nd — UTC says the 3rd.
const AFTER_THE_CLOCKS_CHANGE = "2026-11-03T04:30:00Z"
const READERS = ["Europe/Kyiv", "UTC", "Pacific/Kiritimati", "America/Indiana/Indianapolis"]

const group: Cohort = {
  id: "k1",
  name: "Осень 2026",
  start_date: LATE_ON_THE_31ST,
  end_date: AFTER_THE_CLOCKS_CHANGE,
  // Midnight EDT on October 1: the 1st in Indiana, already the 1st in UTC too.
  enrollment_start: "2026-10-01T04:00:00Z",
  enrollment_end: LATE_ON_THE_31ST,
  start_on: "2026-10-31",
  end_on: "2026-11-02",
  enrollment_start_on: "2026-10-01",
  enrollment_end_on: "2026-10-31",
  status: "active",
  max_students: null,
  created_by: null,
  created_at: "2026-09-01T00:00:00Z",
  updated_at: null,
  course_ids: [],
  student_count: 0,
}

const course = {
  id: "c-1",
  title: "Acts",
  description: null,
  image_url: null,
  status: "published",
  access_mode: "public",
  created_at: "2026-09-01T00:00:00Z",
  updated_at: "2026-09-01T00:00:00Z",
  deleted_at: null,
  enrollment_start: null,
  enrollment_end: null,
  modules: [],
} as unknown as Course

describe("the day a group is dated", () => {
  afterEach(() => {
    setDisplayTimeZone(null)
  })

  it("is the school's day whatever the reader's zone, and the reader's without one", () => {
    for (const zone of READERS) {
      setDisplayTimeZone(zone)
      expect(formatDay("2026-10-31", LATE_ON_THE_31ST)).toBe("2026-10-31")
      expect(formatDay("2026-11-02", AFTER_THE_CLOCKS_CHANGE)).toBe("2026-11-02")
    }
    // A response from an older server: the instant's day on the reader's clock.
    setDisplayTimeZone("Europe/Kyiv")
    expect(formatDay(null, LATE_ON_THE_31ST)).toBe("2026-11-01")
    setDisplayTimeZone("America/Indiana/Indianapolis")
    expect(formatDay(undefined, AFTER_THE_CLOCKS_CHANGE)).toBe("2026-11-02")
    expect(formatDay(null, null)).toBe("")
  })
})

describe("a group's page, read in Kyiv", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru")
    setDisplayTimeZone("Europe/Kyiv")
    vi.restoreAllMocks()
    vi.spyOn(cohortsService, "listCohortStudents").mockResolvedValue([])
  })
  afterEach(() => {
    setDisplayTimeZone(null)
  })

  function open() {
    return render(
      <I18nextProvider i18n={i18n}>
        <MemoryRouter initialEntries={["/admin/cohorts/k1"]}>
          <Routes>
            <Route path="/admin/cohorts/:cohortId" element={<CohortDetailPage />} />
          </Routes>
        </MemoryRouter>
      </I18nextProvider>,
    )
  }

  it("heads the page with the school's days", async () => {
    vi.spyOn(cohortsService, "getCohort").mockResolvedValue(group)
    open()
    expect(await screen.findByText("2026-10-31 — 2026-11-02")).toBeInTheDocument()
  })

  it("falls back to the reader's days for a response from an older server", async () => {
    vi.spyOn(cohortsService, "getCohort").mockResolvedValue({ ...group, start_on: undefined, end_on: undefined })
    open()
    expect(await screen.findByText("2026-11-01 — 2026-11-03")).toBeInTheDocument()
  })
})

describe("the course page a student enrols from, read in Kyiv", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("en")
    setDisplayTimeZone("Europe/Kyiv")
  })
  afterEach(() => {
    setDisplayTimeZone(null)
  })

  it("dates the group and its enrolment window on the school's clock", () => {
    render(
      <I18nextProvider i18n={i18n}>
        <MemoryRouter>
          <NotEnrolledView
            course={course}
            cohorts={[group]}
            isOwner={false}
            isSignedIn
            enrolling={false}
            onEnroll={() => {}}
          />
        </MemoryRouter>
      </I18nextProvider>,
    )
    expect(screen.getByText(/Oct 31, 2026 — Nov 2, 2026/)).toBeInTheDocument()
    expect(screen.getByText("Enrollment: Oct 1, 2026 — Oct 31, 2026")).toBeInTheDocument()
    expect(screen.queryByText(/Nov 1, 2026/)).not.toBeInTheDocument()
  })
})
