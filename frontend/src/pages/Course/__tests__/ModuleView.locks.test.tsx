import { render, screen } from "@testing-library/react"
import { I18nextProvider } from "react-i18next"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"
import i18n from "@/i18n/config"
import { coursesService } from "@/services/courses"

vi.mock("@/context/useAuth", () => ({
  useAuth: () => ({ user: { id: "s1", role: "student", email: "s@example.com" }, loading: false }),
}))

import ModuleView from "../ModuleView"

const chapter = (id: string, module_id: string, order_index: number, chapter_type: string, is_locked = false) => ({
  id,
  module_id,
  course_id: "k1",
  title: id === "c3" ? "Антиохия" : `Урок ${id}`,
  chapter_type,
  order_index,
  is_locked,
  requires_completion: false,
  deleted_at: null,
})

const m1 = { id: "m1", course_id: "k1", title: "Иерусалим", order_index: 0, deleted_at: null, chapters: [chapter("c1", "m1", 0, "reading"), chapter("c2", "m1", 1, "exam")] }
// The standard gate: the next module's first lesson opens after the exam.
const m2 = { id: "m2", course_id: "k1", title: "Миссия", order_index: 1, deleted_at: null, chapters: [chapter("c3", "m2", 0, "reading", true)] }

describe("the module page", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru")
    vi.restoreAllMocks()
    vi.spyOn(coursesService, "getModule").mockResolvedValue(m2 as never)
    vi.spyOn(coursesService, "getCourse").mockResolvedValue({ id: "k1", title: "Деяния", modules: [m1, m2], chapters: [] } as never)
    vi.spyOn(coursesService, "getReadingTime").mockResolvedValue({ chapters: {}, total_minutes: 0 })
  })

  it("opens the first lesson of a module once the exam before it, in the course, is passed", async () => {
    vi.spyOn(coursesService, "getMyChapterProgress").mockResolvedValue(["c1", "c2"])
    render(
      <I18nextProvider i18n={i18n}>
        <MemoryRouter initialEntries={["/courses/k1/modules/m2"]}>
          <Routes>
            <Route path="/courses/:courseId/modules/:moduleId" element={<ModuleView />} />
          </Routes>
        </MemoryRouter>
      </I18nextProvider>,
    )
    expect(await screen.findByRole("link", { name: /Антиохия/ })).toBeInTheDocument()
  })

  it("keeps it locked while the exam is still to do", async () => {
    vi.spyOn(coursesService, "getMyChapterProgress").mockResolvedValue(["c1"])
    render(
      <I18nextProvider i18n={i18n}>
        <MemoryRouter initialEntries={["/courses/k1/modules/m2"]}>
          <Routes>
            <Route path="/courses/:courseId/modules/:moduleId" element={<ModuleView />} />
          </Routes>
        </MemoryRouter>
      </I18nextProvider>,
    )
    expect(await screen.findByText("Антиохия")).toBeInTheDocument()
    expect(screen.queryByRole("link", { name: /Антиохия/ })).not.toBeInTheDocument()
  })

  it("fails open when the course order cannot be had", async () => {
    vi.spyOn(coursesService, "getCourse").mockRejectedValue(new Error("offline"))
    vi.spyOn(coursesService, "getMyChapterProgress").mockResolvedValue(["c1", "c2"])
    render(
      <I18nextProvider i18n={i18n}>
        <MemoryRouter initialEntries={["/courses/k1/modules/m2"]}>
          <Routes>
            <Route path="/courses/:courseId/modules/:moduleId" element={<ModuleView />} />
          </Routes>
        </MemoryRouter>
      </I18nextProvider>,
    )
    expect(await screen.findByRole("link", { name: /Антиохия/ })).toBeInTheDocument()
  })
})
