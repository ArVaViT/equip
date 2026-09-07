import type { ReactNode } from "react"
import { render, screen } from "@testing-library/react"
import { I18nextProvider } from "react-i18next"
import { MemoryRouter } from "react-router-dom"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"
import i18n from "@/i18n/config"
import { gradesService } from "@/services/grades"
import { CertificateBlockers } from "../CertificateBlockers"
import { readCourseStructure } from "@/lib/courseStructure"
import type { CertificateBlocker, Chapter, Course } from "@/types"

const chapter = (over: Partial<Chapter>): Chapter =>
  ({
    course_id: "c1",
    module_id: null,
    order_index: 0,
    chapter_type: "assignment",
    ...over,
  }) as Chapter

/** A course whose work sits in a module, and a course whose work does not. */
const GROUPED = readCourseStructure({
  id: "c1",
  modules: [
    {
      id: "m1",
      course_id: "c1",
      title: "Модуль 1",
      description: null,
      order_index: 0,
      due_date: null,
      chapters: [chapter({ id: "ch1", module_id: "m1", title: "Эссе о благодати" })],
    },
  ],
} as unknown as Course)

const LOOSE = readCourseStructure({
  id: "c1",
  modules: [],
  chapters: [chapter({ id: "ch1", title: "Эссе о благодати" })],
} as unknown as Course)

function Wrapper({ children }: { children: ReactNode }) {
  return (
    <I18nextProvider i18n={i18n}>
      <MemoryRouter>{children}</MemoryRouter>
    </I18nextProvider>
  )
}

function show(blockers: CertificateBlocker[], structure = GROUPED) {
  return render(<CertificateBlockers blockers={blockers} structure={structure} courseId="c1" />, {
    wrapper: Wrapper,
  })
}

describe("CertificateBlockers", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru")
    vi.restoreAllMocks()
  })

  it("says nothing when nothing stands in the way", () => {
    const { container } = show([])
    expect(container).toBeEmptyDOMElement()
  })

  it("names the work and links to it", () => {
    show([{ code: "work_not_graded", params: { count: 1 }, chapter_ids: ["ch1"] }])

    expect(screen.getByText(/ещё не проверена/)).toBeInTheDocument()
    // The link carries the chapter's own title: "открыть работу 1" makes a
    // student count rows to work out which one it means.
    expect(screen.getByRole("link", { name: "Эссе о благодати" })).toHaveAttribute(
      "href",
      "/courses/c1/chapters/ch1",
    )
  })

  it("names work that is in no module — it used to vanish from the list", () => {
    // The lookup walked `modules[].chapters`, so an assignment written
    // straight into the course was in no lookup: the sentence still said a
    // piece of work was unread, and the link naming *which* piece silently
    // dropped out. On a course of four lessons and no modules that meant
    // every link disappeared from the only card that explains the refusal.
    show([{ code: "work_not_graded", params: { count: 1 }, chapter_ids: ["ch1"] }], LOOSE)

    expect(screen.getByRole("link", { name: "Эссе о благодати" })).toHaveAttribute(
      "href",
      "/courses/c1/chapters/ch1",
    )
  })

  it("says the score will still rise while work is unread", () => {
    show([
      {
        code: "below_threshold",
        params: { final_score: 64, pass_threshold: 70, provisional: true },
        chapter_ids: [],
      },
    ])

    // Итоговая counts unmarked work as zero. Stated flatly, «64% < 70%» tells a
    // student they are failing when in fact nobody has finished reading them.
    expect(screen.getByText(/результат ещё вырастет/)).toBeInTheDocument()
  })

  it("states the score plainly once everything has been marked", () => {
    show([
      {
        code: "below_threshold",
        params: { final_score: 64, pass_threshold: 70, provisional: false },
        chapter_ids: [],
      },
    ])

    expect(screen.getByText(/ниже проходного/)).toBeInTheDocument()
    expect(screen.queryByText(/ещё вырастет/)).not.toBeInTheDocument()
  })

  it("still says something when the backend sends a code this build has no words for", () => {
    // The gate is enforced by the backend. A frontend that renders a raw key
    // (or nothing at all) next to a blocked certificate leaves the student
    // with a refusal and no sentence — the exact failure this card exists to
    // prevent.
    show([{ code: "some_future_rule", params: {}, chapter_ids: [] }])

    expect(screen.getByText(/уточните у преподавателя/)).toBeInTheDocument()
  })

  it("drops a link to a chapter this page does not know about", () => {
    show([{ code: "work_not_graded", params: { count: 1 }, chapter_ids: ["ch-deleted"] }])

    expect(screen.getByText(/ещё не проверена/)).toBeInTheDocument()
    expect(screen.queryByRole("link")).not.toBeInTheDocument()
  })

  it("offers the recovery path when the student is genuinely stuck", async () => {
    const request = vi
      .spyOn(gradesService, "requestRetake")
      .mockResolvedValue({ status: "requested" })
    show([
      {
        code: "quizzes_not_passed",
        params: { count: 1 },
        chapter_ids: [],
      },
    ])

    await userEvent.click(screen.getByRole("button", { name: /Запросить пересдачу/ }))

    expect(request).toHaveBeenCalledWith("c1")
    // And it stops offering, so an anxious student does not send it five times.
    expect(await screen.findByRole("button", { name: /Запрос отправлен/ })).toBeDisabled()
  })

  it("does not offer a retake for work nobody has read yet", () => {
    show([
      { code: "work_not_graded", params: { count: 2 }, chapter_ids: [] },
      {
        code: "below_threshold",
        params: { final_score: 0, pass_threshold: 70, provisional: true },
        chapter_ids: [],
      },
    ])

    // The score is a floor, not a verdict. A retake request against it asks the
    // teacher to fix a number that is not yet their decision — which is a
    // student chasing their own homework.
    expect(screen.queryByRole("button")).not.toBeInTheDocument()
  })

  it("does not offer a retake for work that was never handed in", () => {
    show([{ code: "work_not_submitted", params: { count: 1 }, chapter_ids: [] }])

    expect(screen.queryByRole("button")).not.toBeInTheDocument()
  })
})
