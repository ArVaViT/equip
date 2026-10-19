import type { ReactNode } from "react"
import { render, screen } from "@testing-library/react"
import { I18nextProvider } from "react-i18next"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"

import i18n from "@/i18n/config"
import type { Cohort, Course } from "@/types"

/**
 * The course page takes «may I edit this?» from the server's
 * `viewer_can_edit`, not from comparing the reader's id with `created_by`.
 * The comparison meant every guest was sent the author's account id; the
 * server already knew the answer and now says it.
 */

const getCourse = vi.fn<(id: string) => Promise<Course>>()

vi.mock("@/services/courses", () => ({
  coursesService: {
    getCourse: (id: string) => getCourse(id),
    getEnrollmentStatus: () => Promise.resolve({ enrolled: false, enrollment: null }),
    getCourseCohorts: () => Promise.resolve([] as Cohort[]),
    getCourseCertificate: () => Promise.resolve(null),
    getMyChapterProgress: () => Promise.resolve([] as string[]),
    getCalendarEvents: () => Promise.resolve([]),
  },
}))
vi.mock("@/services/storage", () => ({ storageService: { listCourseMaterials: () => Promise.resolve([]) } }))
vi.mock("@/context/useAuth", () => ({
  useAuth: () => ({ user: { id: "t-1", role: "teacher" } }),
}))
vi.mock("@/lib/recentlyViewed", () => ({ recordCourseView: () => {} }))
vi.mock("@/lib/toast", () => ({ toast: vi.fn() }))

const { default: CourseDetail } = await import("../CourseDetail")

/** A draft: its author sees the outline and a way back to the editor; a reader sees neither. */
const draft = (over: Partial<Course>): Course =>
  ({
    id: "c1",
    title: "Acts of the Apostles",
    description: "Six questions.",
    image_url: null,
    status: "draft",
    access_mode: "public",
    created_at: "2026-09-01T00:00:00Z",
    updated_at: "2026-09-01T00:00:00Z",
    deleted_at: null,
    enrollment_start: null,
    enrollment_end: null,
    modules: [],
    chapters: [],
    ...over,
  }) as unknown as Course

function Page({ children }: { children: ReactNode }) {
  return (
    <I18nextProvider i18n={i18n}>
      <MemoryRouter initialEntries={["/courses/c1"]}>
        <Routes>
          <Route path="/courses/:id" element={children} />
        </Routes>
      </MemoryRouter>
    </I18nextProvider>
  )
}

describe("CourseDetail — who may edit", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("en")
    getCourse.mockReset()
  })

  it("the server's yes opens the author's view", async () => {
    getCourse.mockResolvedValue(draft({ viewer_can_edit: true }))
    render(
      <Page>
        <CourseDetail />
      </Page>,
    )
    expect(await screen.findByText("Back to the course editor")).toBeInTheDocument()
  })

  it("a matching id is not a yes: the author's id is not even sent to a reader", async () => {
    // The old client-side rule would have called this reader the owner.
    getCourse.mockResolvedValue(draft({ created_by: "t-1", viewer_can_edit: false }))
    render(
      <Page>
        <CourseDetail />
      </Page>,
    )
    expect(await screen.findByText("Acts of the Apostles")).toBeInTheDocument()
    expect(screen.queryByText("Back to the course editor")).not.toBeInTheDocument()
  })
})
