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
