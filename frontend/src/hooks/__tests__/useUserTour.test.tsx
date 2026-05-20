import { act, render } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import type { ReactNode } from "react"
import { I18nextProvider } from "react-i18next"
import i18n from "@/i18n/config"
import { AuthContext } from "@/context/auth-context"
import { useUserTour } from "../useUserTour"
import type { User } from "@/types"

// Hoisted mock so the spy survives across re-renders without leaking
// state between tests.
const driveMock = vi.fn()
const destroyMock = vi.fn()
const createTourMock = vi.fn(() => ({ drive: driveMock, destroy: destroyMock }))

vi.mock("@/lib/tour", () => ({
  createEditorialTour: (...args: unknown[]) => createTourMock(...(args as [])),
}))

function makeUser(id: string): User {
  return {
    id,
    email: `${id}@example.com`,
    full_name: "Test User",
    avatar_url: null,
    role: "student",
    preferred_locale: "en",
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  }
}

interface ExposedTour {
  start: () => void
  alreadySeen: boolean
}

function Harness({
  expose,
  tourId,
}: {
  expose: (tour: ExposedTour) => void
  tourId: string
}) {
  const tour = useUserTour({
    tourId,
    steps: [{ popover: { title: "Hi", description: "There" } }],
  })
  expose(tour)
  return null
}

function renderWithUser(userId: string | null, tourId: string) {
  let captured: ExposedTour | null = null
  const wrapper = ({ children }: { children: ReactNode }) => (
    <I18nextProvider i18n={i18n}>
      <AuthContext.Provider
        value={{
          user: userId ? makeUser(userId) : null,
          loading: false,
          login: vi.fn(),
          register: vi.fn(),
          signInWithGoogle: vi.fn(),
          resetPassword: vi.fn(),
          logout: vi.fn(),
          refreshUser: vi.fn(),
        }}
      >
        {children}
      </AuthContext.Provider>
    </I18nextProvider>
  )
  render(
    <Harness
      expose={(t) => {
        captured = t
      }}
      tourId={tourId}
    />,
    { wrapper },
  )
  return captured!
}

beforeEach(() => {
  window.localStorage.clear()
  driveMock.mockClear()
  destroyMock.mockClear()
  createTourMock.mockClear()
})

afterEach(() => {
  vi.clearAllMocks()
})

describe("useUserTour", () => {
  it("reports alreadySeen=false when the flag is missing", () => {
    const tour = renderWithUser("user-a", "student-dashboard-v1")
    expect(tour.alreadySeen).toBe(false)
  })

  it("reports alreadySeen=true when a flag is set for this user+tour", () => {
    window.localStorage.setItem("equip.tour.seen.user-a.student-dashboard-v1", "1")
    const tour = renderWithUser("user-a", "student-dashboard-v1")
    expect(tour.alreadySeen).toBe(true)
  })

  it("scopes the flag by user — second account on same device sees fresh tour", () => {
    // Account A has finished the tour
    window.localStorage.setItem("equip.tour.seen.user-a.student-dashboard-v1", "1")
    // Account B should still get alreadySeen=false
    const tourB = renderWithUser("user-b", "student-dashboard-v1")
    expect(tourB.alreadySeen).toBe(false)
  })

  it("scopes the flag by tour id — student tour completion doesn't suppress teacher tour", () => {
    window.localStorage.setItem("equip.tour.seen.user-a.student-dashboard-v1", "1")
    const teacherTour = renderWithUser("user-a", "teacher-dashboard-v1")
    expect(teacherTour.alreadySeen).toBe(false)
  })

  it("start() builds + drives a tour", () => {
    const tour = renderWithUser("user-a", "student-dashboard-v1")
    act(() => {
      tour.start()
    })
    expect(createTourMock).toHaveBeenCalledTimes(1)
    expect(driveMock).toHaveBeenCalledTimes(1)
  })

  it("no-ops when there is no signed-in user", () => {
    const tour = renderWithUser(null, "student-dashboard-v1")
    // The hook never wrote a flag because we have nobody to scope by.
    expect(tour.alreadySeen).toBe(false)
    act(() => {
      tour.start()
    })
    // start() still wires up driver.js — calling it manually with no
    // user is allowed (the trigger source already gated). The flag
    // just never gets written because flagKey returns null.
    expect(createTourMock).toHaveBeenCalledTimes(1)
  })
})
