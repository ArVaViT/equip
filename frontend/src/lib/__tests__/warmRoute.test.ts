import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

// The page modules are what the warm-up imports; stubbed so the test checks
// which ones it asks for, not what they render. A module is evaluated once
// per run, so `loaded` accumulates and each case names a different chunk.
const { loaded, phone } = vi.hoisted(() => ({ loaded: new Set<string>(), phone: { value: true } }))
vi.mock("@/pages/Dashboard/DashboardPage", () => (loaded.add("DashboardPage"), {}))
vi.mock("@/pages/Dashboard/PublicLanding", () => (loaded.add("PublicLanding"), {}))
vi.mock("@/pages/Courses/CoursesPage", () => (loaded.add("CoursesPage"), {}))
vi.mock("@/pages/Course/CourseDetail", () => (loaded.add("CourseDetail"), {}))
vi.mock("@/pages/Course/ChapterView", () => (loaded.add("ChapterView"), {}))

vi.mock("@/pages/Dashboard/landing/phoneCut", () => ({ isPhone: () => phone.value }))

import { warmRoute } from "../warmRoute"

function posterPreloads() {
  return document.head.querySelectorAll('link[rel="preload"][as="image"]')
}

async function settle() {
  // Dynamic imports resolve on later ticks.
  for (let i = 0; i < 5; i++) await Promise.resolve()
  await new Promise((r) => setTimeout(r, 0))
}

describe("warmRoute", () => {
  beforeEach(() => {
    phone.value = true
    localStorage.clear()
    document.head.innerHTML = ""
  })
  afterEach(() => localStorage.clear())

  it("preloads the phone tour poster at high priority for an anonymous visitor on /", () => {
    warmRoute("/")
    const links = posterPreloads()
    expect(links).toHaveLength(1)
    expect(links[0]?.getAttribute("href")).toBe("/video/tour-poster-vertical.jpg")
    expect(links[0]?.getAttribute("fetchpriority")).toBe("high")
  })

  it("does not preload the poster on a wide screen", () => {
    phone.value = false
    warmRoute("/")
    expect(posterPreloads()).toHaveLength(0)
  })

  it("does not preload the landing for a stored session — that visitor gets the dashboard", () => {
    localStorage.setItem("sb-abc-auth-token", '{"access_token":"x"}')
    warmRoute("/")
    expect(posterPreloads()).toHaveLength(0)
  })

  it("leaves other pages alone", () => {
    warmRoute("/teacher")
    warmRoute("/courses/abc/edit")
    expect(posterPreloads()).toHaveLength(0)
  })

  it.each([
    ["/courses", "CoursesPage"],
    ["/courses/abc", "CourseDetail"],
    ["/courses/abc/modules/m/chapters/def", "ChapterView"],
  ])("fetches the route chunk for %s", async (path, chunk) => {
    warmRoute(path)
    await settle()
    expect(loaded.has(chunk)).toBe(true)
  })
})
