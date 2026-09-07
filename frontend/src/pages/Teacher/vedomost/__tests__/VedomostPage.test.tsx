import { render, screen } from "@testing-library/react"
import { I18nextProvider } from "react-i18next"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"
import i18n from "@/i18n/config"
import { gradesService } from "@/services/grades"
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
})
