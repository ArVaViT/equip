import type { ReactNode } from "react"
import { fireEvent, render, screen } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { I18nextProvider } from "react-i18next"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import i18n from "@/i18n/config"
import CourseCard from "../CourseCard"
import type { Course } from "@/types"

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

  it("shows the module count", () => {
    renderCard(
      makeCourse({
        modules: [
          { id: "m1", course_id: "c-1", title: "A", description: null, order_index: 0, due_date: null },
          { id: "m2", course_id: "c-1", title: "B", description: null, order_index: 1, due_date: null },
        ],
      }),
    )
    expect(screen.getByText(/2 modules/i)).toBeInTheDocument()
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
})
