import { render, screen, waitFor } from "@testing-library/react"
import { I18nextProvider } from "react-i18next"
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"
import userEvent from "@testing-library/user-event"

import i18n from "@/i18n/config"
import type { Cohort, Course } from "@/types"
import { GuestPrompt, LockedBlock, type EnrollOffer } from "../GuestPrompt"

const enrollInCourse = vi.fn<(courseId: string, cohortId?: string) => Promise<unknown>>()
vi.mock("@/services/courses", () => ({
  coursesService: { enrollInCourse: (c: string, k?: string) => enrollInCourse(c, k) },
}))
const toast = vi.fn()
vi.mock("@/lib/toast", () => ({ toast: (o: unknown) => toast(o) }))

function Where() {
  const loc = useLocation()
  return <p data-testid="where">{`${loc.pathname}|${JSON.stringify(loc.state)}`}</p>
}

function renderAt(variant: "finish" | "wall" | "enrollFinish" | "enrollWall", offer?: EnrollOffer) {
  render(
    <I18nextProvider i18n={i18n}>
      <MemoryRouter initialEntries={["/courses/c1/chapters/ch2"]}>
        <Routes>
          <Route
            path="/courses/:courseId/chapters/:chapterId"
            element={<GuestPrompt variant={variant} offer={offer} />}
          />
          <Route path="*" element={<Where />} />
        </Routes>
      </MemoryRouter>
    </I18nextProvider>,
  )
}

describe("GuestPrompt", () => {
  it("brings a new account back to the very lesson it left, not to the course page", async () => {
    renderAt("wall")
    await userEvent.click(screen.getByRole("link", { name: i18n.t("guest.register") }))
    expect(screen.getByTestId("where").textContent).toBe('/register|{"from":"/courses/c1/chapters/ch2"}')
  })

  it("and the same for signing in", async () => {
    renderAt("finish")
    await userEvent.click(screen.getByRole("link", { name: i18n.t("guest.signIn") }))
    expect(screen.getByTestId("where").textContent).toBe('/login|{"from":"/courses/c1/chapters/ch2"}')
  })

  it("inside the lesson is one quiet line with no buttons, naming what is there", async () => {
    await i18n.changeLanguage("ru")
    render(
      <I18nextProvider i18n={i18n}>
        <LockedBlock kind="quiz" />
        <LockedBlock kind="assignment" />
        <LockedBlock kind="file" />
      </I18nextProvider>,
    )
    expect(screen.queryByRole("link")).toBeNull()
    expect(screen.queryByRole("button")).toBeNull()
    expect(screen.getByText("Здесь тест — он откроется после записи")).toBeInTheDocument()
    expect(screen.getByText("Здесь задание — оно откроется после записи")).toBeInTheDocument()
    expect(screen.getByText("Здесь файл — он откроется после записи")).toBeInTheDocument()
  })
})

/**
 * Signed in, not enrolled. «Записаться на курс» was a link to the course
 * page, which offered the same button and then left the reader to find the
 * lesson again.
 */
describe("GuestPrompt — enrolling from the lesson", () => {
  const course = { id: "c1", access_mode: "public", enrollment_start: null, enrollment_end: null } as Course
  const openCohort = (id: string): Cohort =>
    ({ id, status: "active", enrollment_start: "2000-01-01T00:00:00Z", enrollment_end: "2999-01-01T00:00:00Z" }) as Cohort
  const onEnrolled = vi.fn()
  const offer = (over: Partial<EnrollOffer> = {}): EnrollOffer => ({
    course,
    cohorts: [],
    // Off the lesson route, so the probe route renders where the prompt went.
    then: "/after",
    onEnrolled,
    ...over,
  })

  beforeEach(async () => {
    await i18n.changeLanguage("ru")
    vi.clearAllMocks()
    enrollInCourse.mockResolvedValue({})
  })

  it("enrols with one press and steps on to the next lesson", async () => {
    renderAt("enrollFinish", offer())
    await userEvent.click(screen.getByRole("button", { name: "Записаться на курс" }))
    expect(enrollInCourse).toHaveBeenCalledWith("c1", undefined)
    await waitFor(() => expect(screen.getByTestId("where").textContent).toBe("/after|null"))
    expect(onEnrolled).toHaveBeenCalledTimes(1)
    expect(toast).toHaveBeenCalledWith({ title: "Вы записаны на курс", variant: "success" })
  })

  it("enrols into the one cohort that is taking students", async () => {
    renderAt("enrollWall", offer({ cohorts: [openCohort("k1")], then: "/courses/c1/chapters/ch2" }))
    await userEvent.click(screen.getByRole("button", { name: "Записаться на курс" }))
    expect(enrollInCourse).toHaveBeenCalledWith("c1", "k1")
  })

  it("says so when enrolling fails, and stays on the lesson", async () => {
    enrollInCourse.mockRejectedValue(new Error("nope"))
    renderAt("enrollFinish", offer())
    await userEvent.click(screen.getByRole("button", { name: "Записаться на курс" }))
    await waitFor(() =>
      expect(toast).toHaveBeenCalledWith({ title: "Не удалось записаться. Попробуйте снова.", variant: "destructive" }),
    )
    expect(onEnrolled).not.toHaveBeenCalled()
    expect(screen.queryByTestId("where")).toBeNull()
    expect(screen.getByRole("button", { name: "Записаться на курс" })).toBeEnabled()
  })

  it("leaves a choice between cohorts, and a course by invitation, to the course page", () => {
    renderAt("enrollFinish", offer({ cohorts: [openCohort("k1"), openCohort("k2")] }))
    expect(screen.getByRole("link", { name: "Записаться на курс" })).toHaveAttribute("href", "/courses/c1")
    expect(screen.queryByRole("button")).toBeNull()
  })

  it("is a link to the course page when the lesson has nothing to offer", () => {
    renderAt("enrollWall")
    expect(screen.getByRole("link", { name: "Записаться на курс" })).toHaveAttribute("href", "/courses/c1")
    expect(enrollInCourse).not.toHaveBeenCalled()
  })
})
