/**
 * A certificate with no course name on it.
 *
 * The page reached for the course title with ``??``, which only catches
 * ``null``. A course that has no title in this reader's language now comes
 * back as an empty string — the deliberate consequence of there being no
 * spare language — and an empty string is not null, so it went straight
 * onto the certificate row. The named fallback beside it, written for
 * exactly this case, never ran.
 */

import { render, screen, waitFor } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import { I18nextProvider } from "react-i18next"
import { MemoryRouter } from "react-router-dom"

import i18n from "@/i18n/config"
import { coursesService } from "@/services/courses"
import CertificatesPage from "../CertificatesPage"

// The page starts a product tour, which needs the auth context. Nothing to
// do with what is being asserted here.
vi.mock("@/hooks/useUserTour", () => ({ useUserTour: () => {} }))

const COURSE_ID = "3f9a1c2e-0000-4000-8000-000000000001"

function renderPage() {
  return render(
    <I18nextProvider i18n={i18n}>
      <MemoryRouter>
        <CertificatesPage />
      </MemoryRouter>
    </I18nextProvider>,
  )
}

function seed(title: string) {
  vi.spyOn(coursesService, "getMyCertificates").mockResolvedValue([
    {
      id: "cert-1",
      course_id: COURSE_ID,
      user_id: "u-1",
      issued_at: "2026-05-01T00:00:00Z",
      certificate_number: "EQ-0001",
    },
  ] as never)
  vi.spyOn(coursesService, "getMyCourses").mockResolvedValue([
    { course_id: COURSE_ID, course: { id: COURSE_ID, title } },
  ] as never)
}

describe("the course name on a certificate", () => {
  it("falls back to the identifier when the title is empty in this language", async () => {
    seed("")
    renderPage()
    // The fallback names the course by its id rather than printing nothing.
    await waitFor(() => expect(screen.getByText(new RegExp(COURSE_ID.slice(0, 8)))).toBeInTheDocument())
  })

  it("prints the title when there is one", async () => {
    seed("The Acts of the Apostles")
    renderPage()
    await waitFor(() => expect(screen.getByText("The Acts of the Apostles")).toBeInTheDocument())
  })
})

describe("a certificate whose course has since been deleted", () => {
  /**
   * The certificate keeps `archived_course_title` for exactly this case —
   * written when the request was made, so the name survives the course.
   * The list ignored it and printed "Course —", while
   * `CertificateDocument` printed the real name on the certificate itself.
   * Fourteen rows in production on 2026-08-31 read that way.
   */
  it("uses the archived title instead of a dash", async () => {
    vi.spyOn(coursesService, "getMyCertificates").mockResolvedValue([
      {
        id: "cert-archived",
        course_id: null,
        archived_course_title: "Проверка оценок (тест)",
        user_id: "u-1",
        status: "rejected",
        requested_at: "2026-08-27T17:31:04Z",
      },
    ] as never)
    vi.spyOn(coursesService, "getMyCourses").mockResolvedValue([] as never)

    renderPage()

    await waitFor(() =>
      expect(screen.getByText("Проверка оценок (тест)")).toBeInTheDocument(),
    )
  })
})

describe("how many certificates the page says were earned", () => {
  /**
   * It counted every row, so a reader whose requests had all been rejected
   * was told "14 certificates earned" above fourteen cards each marked
   * "Rejected". Exactly what production showed today.
   */
  function seedStatuses(statuses: string[]) {
    vi.spyOn(coursesService, "getMyCertificates").mockResolvedValue(
      statuses.map((status, i) => ({
        id: `cert-${i}`,
        course_id: null,
        archived_course_title: `Course ${i}`,
        user_id: "u-1",
        status,
        issued_at: status === "approved" ? "2026-05-01T00:00:00Z" : null,
      })) as never,
    )
    vi.spyOn(coursesService, "getMyCourses").mockResolvedValue([] as never)
  }

  it("does not count a rejected request as earned", async () => {
    seedStatuses(["rejected", "rejected", "rejected"])
    renderPage()
    await waitFor(() => expect(screen.getAllByText(/Course 0/).length).toBeGreaterThan(0))
    expect(screen.getByText(i18n.t("certificates.subtitle", { count: 0 }))).toBeInTheDocument()
  })

  it("counts only the ones actually awarded", async () => {
    seedStatuses(["approved", "rejected", "pending", "approved"])
    renderPage()
    await waitFor(() => expect(screen.getAllByText(/Course 0/).length).toBeGreaterThan(0))
    expect(screen.getByText(i18n.t("certificates.subtitle", { count: 2 }))).toBeInTheDocument()
  })
})
