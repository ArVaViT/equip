/**
 * The first-run picker offers only what a newcomer can join now. A course
 * whose enrolment window had closed was offered, and the first thing the
 * person did on the platform was refused with no reason (2026-10-03).
 */
import type { ReactNode } from "react"
import { render, screen } from "@testing-library/react"
import { I18nextProvider } from "react-i18next"
import { MemoryRouter } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"

import i18n from "@/i18n/config"
import { coursesService } from "@/services/courses"
import type { Course } from "@/types"
import { CoursePickerStep } from "../CoursePickerStep"

function course(id: string, title: string, over: Partial<Course> = {}): Course {
  return {
    id,
    title,
    description: null,
    image_url: null,
    status: "published",
    access_mode: "public",
    enrollment_start: null,
    enrollment_end: null,
    ...over,
  } as Course
}

function Wrapper({ children }: { children: ReactNode }) {
  return (
    <I18nextProvider i18n={i18n}>
      <MemoryRouter>{children}</MemoryRouter>
    </I18nextProvider>
  )
}

describe("CoursePickerStep", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("en")
    vi.restoreAllMocks()
  })

  it("leaves out a course whose window is closed or not yet open", async () => {
    vi.spyOn(coursesService, "getCourses").mockResolvedValue([
      course("open", "Acts"),
      course("closed", "Romans", { enrollment_end: "2020-01-01T00:00:00Z" }),
      course("later", "Hebrews", { enrollment_start: "2999-01-01T00:00:00Z" }),
    ])
    render(<CoursePickerStep onEnrolled={vi.fn()} onSkip={vi.fn()} />, { wrapper: Wrapper })

    expect(await screen.findByText("Acts")).toBeInTheDocument()
    expect(screen.queryByText("Romans")).not.toBeInTheDocument()
    expect(screen.queryByText("Hebrews")).not.toBeInTheDocument()
  })
})
