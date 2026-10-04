import type { ReactNode } from "react"
import { fireEvent, render, screen } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { I18nextProvider } from "react-i18next"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import i18n from "@/i18n/config"
import { axe } from "@/test/a11y"
import CourseCard from "../CourseCard"
import type { Chapter, Course } from "@/types"

function makeCourse(overrides: Partial<Course> = {}): Course {
  return {
    id: "c-1",
    title: "Test Course",
    description: "Short course description",
    image_url: null,
    status: "published",
    access_mode: "public",
    created_by: "teacher-1",
    created_at: "2025-01-01T00:00:00Z",
    updated_at: "2025-01-01T00:00:00Z",
    deleted_at: null,
    enrollment_start: null,
    enrollment_end: null,
    modules: [],
    ...overrides,
  }
}

function TestWrapper({ children }: { children: ReactNode }) {
  return (
    <I18nextProvider i18n={i18n}>
      <MemoryRouter>{children}</MemoryRouter>
    </I18nextProvider>
  )
}

function renderCard(course: Course) {
  return render(<CourseCard course={course} />, { wrapper: TestWrapper })
}

describe("CourseCard", () => {
  beforeEach(() => {
    vi.stubEnv("VITE_SUPABASE_URL", "https://abc.supabase.co")
  })

  afterEach(() => {
    vi.unstubAllEnvs()
  })

  it("renders the title and description", () => {
    renderCard(makeCourse({ title: "Genesis", description: "Intro course" }))
    expect(screen.getByText("Genesis")).toBeInTheDocument()
    expect(screen.getByText("Intro course")).toBeInTheDocument()
  })

  it("counts lessons, not modules: four lessons and no module is not \"0 modules\"", async () => {
    await i18n.changeLanguage("en")
    renderCard(makeCourse({ modules: [], chapter_count: 4, module_count: 0 }))
    expect(screen.getByText("4 lessons")).toBeInTheDocument()
    expect(screen.queryByText(/modules?/i)).toBeNull()
  })

  it("says nothing rather than \"0 lessons\" for an empty course", async () => {
    await i18n.changeLanguage("en")
    renderCard(makeCourse({ modules: [], chapter_count: 0 }))
    expect(screen.queryByText(/lessons?$/)).toBeNull()
  })

  it("renders a placeholder icon when there is no image", () => {
    const { container } = renderCard(makeCourse({ image_url: null }))
    expect(container.querySelector("img")).toBeNull()
  })

  it("renders an image when image_url is provided", () => {
    renderCard(
      makeCourse({
        image_url: "https://abc.supabase.co/storage/v1/object/public/covers/c.jpg",
        title: "With Cover",
      }),
    )
    const img = screen.getByAltText("With Cover") as HTMLImageElement
    // ``toProxyImage`` rewrites Supabase public URLs to /img/ so AdBlock
    // doesn't block our own course art.
    expect(img.getAttribute("src")).toBe("/img/covers/c.jpg")
  })

  it("falls back to the placeholder icon when the image fails to load", () => {
    const { container } = renderCard(
      makeCourse({
        image_url: "https://example.com/broken.jpg",
        title: "Broken",
      }),
    )
    const img = screen.getByAltText("Broken") as HTMLImageElement
    expect(img).toBeInTheDocument()

    // ``fireEvent.error`` wraps the dispatch in act() so React flushes the
    // setImgError(true) state update synchronously.
    fireEvent.error(img)
    expect(container.querySelector("img")).toBeNull()
  })

  it("marks a closed course «by invitation» to an outsider, and «for members of …» to a member", async () => {
    // To a member «По приглашению» read as "not for you" on a course they
    // could open (2026-10-03).
    await i18n.changeLanguage("ru")
    const closed = makeCourse({ access_mode: "institute", organization_name: "UCOAT" })
    renderCard(closed)
    expect(screen.getByText("По приглашению")).toBeInTheDocument()

    render(<CourseCard course={closed} viewerIsMember />, { wrapper: TestWrapper })
    expect(screen.getByText("Для участников UCOAT")).toBeInTheDocument()
    await i18n.changeLanguage("en")
  })

  it("says «for members» without a name when the card has no organization to name", async () => {
    await i18n.changeLanguage("ru")
    render(<CourseCard course={makeCourse({ access_mode: "institute" })} viewerIsMember />, { wrapper: TestWrapper })
    expect(screen.getByText("Для участников")).toBeInTheDocument()
    await i18n.changeLanguage("en")
  })

  it("links to the course detail page", () => {
    renderCard(makeCourse({ id: "genesis-intro" }))
    const link = screen.getByRole("link")
    expect(link).toHaveAttribute("href", "/courses/genesis-intro")
  })

  it('shows an "Enrollment closed" badge when end is in the past', () => {
    const pastDate = new Date(Date.now() - 86_400_000).toISOString()
    renderCard(
      makeCourse({
        enrollment_start: null,
        enrollment_end: pastDate,
      }),
    )
    expect(screen.getByText(/enrollment closed/i)).toBeInTheDocument()
  })

  it('shows an "Enrolling now" badge when within the window', () => {
    const pastStart = new Date(Date.now() - 86_400_000).toISOString()
    const futureEnd = new Date(Date.now() + 86_400_000).toISOString()
    renderCard(
      makeCourse({
        enrollment_start: pastStart,
        enrollment_end: futureEnd,
      }),
    )
    expect(screen.getByText(/enrolling now/i)).toBeInTheDocument()
  })

  it("falls back to the lessons nested under modules when the list did not count", async () => {
    await i18n.changeLanguage("en")
    const lessons = (n: number) => Array.from({ length: n }, (_, i) => ({ id: `ch-${i}` })) as unknown as Chapter[]
    renderCard(
      makeCourse({
        modules: [
          { id: "m1", course_id: "c-1", title: "A", description: null, order_index: 0, due_date: null, chapters: lessons(2) },
          { id: "m2", course_id: "c-1", title: "B", description: null, order_index: 1, due_date: null, chapters: lessons(1) },
        ],
      }),
    )
    expect(screen.getByText("3 lessons")).toBeInTheDocument()
  })

  it('shows the "By invitation" badge on institute courses instead of the enrollment-window badge', () => {
    const futureEnd = new Date(Date.now() + 86_400_000).toISOString()
    renderCard(
      makeCourse({
        access_mode: "institute",
        enrollment_start: null,
        enrollment_end: futureEnd,
      }),
    )
    expect(screen.getByText(/by invitation/i)).toBeInTheDocument()
    expect(screen.queryByText(/enrolling now/i)).not.toBeInTheDocument()
  })

  it("renders without any a11y violations (open enrollment + cover image)", async () => {
    // CourseCard is rendered up to ~50 times in the catalog grid; a
    // violation here is a violation 50x. Pin axe-clean rendering for
    // the representative state.
    const futureEnd = new Date(Date.now() + 86_400_000).toISOString()
    const { container } = renderCard(
      makeCourse({
        title: "Genesis Foundations",
        description: "A 12-lesson intro to the book of Genesis.",
        image_url: "https://abc.supabase.co/storage/v1/object/public/covers/g.jpg",
        enrollment_start: new Date(Date.now() - 86_400_000).toISOString(),
        enrollment_end: futureEnd,
        modules: [
          { id: "m1", course_id: "c-1", title: "A", description: null, order_index: 0, due_date: null },
          { id: "m2", course_id: "c-1", title: "B", description: null, order_index: 1, due_date: null },
        ],
      }),
    )
    expect(await axe(container)).toHaveNoViolations()
  })
})
