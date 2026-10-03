import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { I18nextProvider } from "react-i18next"
import { beforeEach, describe, expect, it, vi } from "vitest"
import i18n from "@/i18n/config"
import { coursesService } from "@/services/courses"
import type { CourseStructure } from "@/lib/courseStructure"
import { CourseTabs } from "../CourseTabs"

const structure = {
  groups: [
    {
      moduleId: "m1",
      module: { id: "m1", title: "Иерусалим" },
      chapters: [
        { id: "c1", title: "Урок 1. Вознесение", chapter_type: "reading" },
        { id: "c2", title: "Эссе о Пятидесятнице", chapter_type: "assignment" },
      ],
    },
  ],
  chapters: [
    { id: "c1", title: "Урок 1. Вознесение", chapter_type: "reading" },
    { id: "c2", title: "Эссе о Пятидесятнице", chapter_type: "assignment" },
  ],
} as unknown as CourseStructure

function renderTabs(hasAbout = true) {
  return render(
    <I18nextProvider i18n={i18n}>
      <CourseTabs courseId="k1" structure={structure} about={<p>Как Дух собрал церковь</p>} hasAbout={hasAbout} />
    </I18nextProvider>,
  )
}

describe("the course before enrolling", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru")
    vi.restoreAllMocks()
    vi.spyOn(coursesService, "getReadingTime").mockResolvedValue({ chapters: { c1: 7 }, total_minutes: 7 })
    vi.spyOn(coursesService, "getAuthor").mockResolvedValue({ name: "Иван Петренко", avatar_url: null, school: "UCOAT" })
  })

  it("opens on what the course is, and shows every lesson by name under «Программа»", async () => {
    renderTabs()
    expect(screen.getByText("Как Дух собрал церковь")).toBeInTheDocument()

    await userEvent.click(screen.getByRole("tab", { name: "Программа" }))
    expect(screen.getByRole("heading", { name: /Иерусалим/ })).toBeInTheDocument()
    expect(screen.getByText("Урок 1. Вознесение")).toBeInTheDocument()
    expect(screen.getByText("Эссе о Пятидесятнице")).toBeInTheDocument()
    // Names, not doors: the lessons open once the reader is enrolled.
    expect(screen.queryByRole("link")).not.toBeInTheDocument()
  })

  it("names the author and the school", async () => {
    renderTabs()
    await userEvent.click(screen.getByRole("tab", { name: "Автор" }))
    expect(await screen.findByText("Иван Петренко")).toBeInTheDocument()
    expect(screen.getByText("UCOAT")).toBeInTheDocument()
  })

  it("leaves «О курсе» out when there is nothing to say, rather than opening onto a blank", () => {
    renderTabs(false)
    expect(screen.queryByRole("tab", { name: "О курсе" })).not.toBeInTheDocument()
    expect(screen.getByRole("tab", { name: "Программа" })).toHaveAttribute("aria-selected", "true")
  })
})
