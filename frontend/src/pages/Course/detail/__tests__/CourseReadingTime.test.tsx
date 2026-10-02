import { render, screen, waitFor } from "@testing-library/react"
import { I18nextProvider } from "react-i18next"
import { beforeEach, describe, expect, it, vi } from "vitest"

import i18n from "@/i18n/config"
import { coursesService } from "@/services/courses"
import { CourseReadingTime } from "../CourseReadingTime"

/** "Can I manage this" has a number for an answer, beside the lesson count. */
function show() {
  return render(
    <I18nextProvider i18n={i18n}>
      <p data-testid="line">
        <CourseReadingTime courseId="c1" />
      </p>
    </I18nextProvider>,
  )
}

describe("CourseReadingTime", () => {
  beforeEach(async () => {
    vi.restoreAllMocks()
    await i18n.changeLanguage("ru")
  })

  it("speaks in minutes under an hour", async () => {
    vi.spyOn(coursesService, "getReadingTime").mockResolvedValue({ chapters: {}, total_minutes: 25 })
    show()
    expect(await screen.findByText(i18n.t("chapter.readingTime", { count: 25 }))).toBeInTheDocument()
  })

  it("shows hours, to the nearest half, above one", async () => {
    vi.spyOn(coursesService, "getReadingTime").mockResolvedValue({ chapters: {}, total_minutes: 143 })
    show()
    expect(await screen.findByText(i18n.t("courseDetail.readingHours", { hours: "2,5" }))).toBeInTheDocument()
    // The eye gets a clock and the short form; the phrase is for the ear.
    expect(screen.getByText("≈ 2,5 ч")).toBeInTheDocument()
  })

  it("says nothing for nothing, or when the request fails", async () => {
    const spy = vi.spyOn(coursesService, "getReadingTime").mockResolvedValue({ chapters: {}, total_minutes: 0 })
    const { unmount } = show()
    await waitFor(() => expect(spy).toHaveBeenCalled())
    expect(screen.getByTestId("line")).toBeEmptyDOMElement()
    unmount()
    spy.mockRejectedValue(new Error("offline"))
    show()
    await waitFor(() => expect(spy).toHaveBeenCalledTimes(2))
    expect(screen.getByTestId("line")).toBeEmptyDOMElement()
  })
})
