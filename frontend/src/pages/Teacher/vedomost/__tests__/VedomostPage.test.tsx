import { render, screen } from "@testing-library/react"
import { I18nextProvider } from "react-i18next"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import i18n from "@/i18n/config"
import { setDisplayTimeZone } from "@/i18n/timeZone"
import { gradesService } from "@/services/grades"
import type { GradeSheet } from "@/types"
import VedomostPage from "../VedomostPage"

/**
 * The one screen on the platform whose primary button is irreversible.
 *
 * `getGradeSheet` answers `null` for a sheet that is still open, and that is
 * the screen with «Закрыть ведомость» on it. A 403 on a colleague's course, a
 * 500, a dropped connection — all used to collapse into that same `null`,
 * so a failure to load offered the button to close a sheet the person had
 * no right to touch. And `close()` had no `catch`: pressing it failed in
 * silence.
 */
function forbidden() {
  return Object.assign(new Error("Forbidden"), {
    isAxiosError: true,
    response: { status: 403, data: {} },
  })
}

function renderPage() {
  return render(
    <I18nextProvider i18n={i18n}>
      <MemoryRouter initialEntries={["/teacher/courses/c1/vedomost"]}>
        <Routes>
          <Route path="/teacher/courses/:courseId/vedomost" element={<VedomostPage />} />
        </Routes>
      </MemoryRouter>
    </I18nextProvider>,
  )
}

describe("VedomostPage", () => {
  beforeEach(async () => {
    vi.restoreAllMocks()
    await i18n.changeLanguage("ru")
  })

  it("offers to close the sheet when the server says it is still open", async () => {
    vi.spyOn(gradesService, "getGradeSheet").mockResolvedValue(null)
    renderPage()
    expect(await screen.findByRole("button", { name: i18n.t("vedomost.close") })).toBeInTheDocument()
  })

  it("does not offer to close anything when the request was refused", async () => {
    vi.spyOn(gradesService, "getGradeSheet").mockRejectedValue(forbidden())
    renderPage()
    // The refusal, in the reader's language, with a way to try again…
    expect(await screen.findByRole("alert")).toHaveTextContent(i18n.t("errors.byStatus.403"))
    expect(screen.getByRole("button", { name: i18n.t("common.tryAgain") })).toBeInTheDocument()
    // …and not the irreversible button.
    expect(screen.queryByRole("button", { name: i18n.t("vedomost.close") })).toBeNull()
    expect(screen.queryByText(i18n.t("vedomost.notClosedTitle"))).toBeNull()
  })

  describe("the dates on the paper", () => {
    afterEach(() => setDisplayTimeZone(null))

    it("are the reader's days, not the browser's", async () => {
      // 20:00 UTC on the 30th is already the 1st in Tokyo; whatever zone the
      // test machine is in (UTC, Indiana), its own clock still says the 30th.
      setDisplayTimeZone("Asia/Tokyo")
      const sheet: GradeSheet = {
        id: "s1",
        course_id: "c1",
        course_title: "Деяния",
        locale: "ru",
        cohort_id: "k1",
        cohort_name: "Осень",
        cohort_start: "2026-09-30T20:00:00Z",
        cohort_end: "2026-12-14T20:00:00Z",
        school_name: null,
        school_city: null,
        teacher_name: null,
        academic_hours: null,
        grading_scheme: "pass_fail",
        pass_threshold: null,
        finalized_at: "2026-09-30T20:00:00Z",
        finalized_by: null,
        reopened_at: null,
        reopen_reason: null,
        corrects_sheet_id: null,
        correction_reason: null,
        rows: [],
      }
      vi.spyOn(gradesService, "getGradeSheet").mockResolvedValue(sheet)
      renderPage()
      expect((await screen.findAllByText(/01\.10\.2026/)).length).toBeGreaterThan(0)
      expect(screen.getAllByText(/15\.12\.2026/).length).toBeGreaterThan(0)
      expect(screen.queryAllByText(/30\.09\.2026/)).toHaveLength(0)
    })
  })
})
