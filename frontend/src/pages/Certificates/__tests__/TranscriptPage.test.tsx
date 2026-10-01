/** The transcript lists issued certificates only, oldest first. */
import { render, screen } from "@testing-library/react"
import { I18nextProvider } from "react-i18next"
import { MemoryRouter } from "react-router-dom"
import { afterEach, describe, expect, it, vi } from "vitest"

import i18n from "@/i18n/config"
import { coursesService } from "@/services/courses"
import type { Certificate } from "@/types"
import TranscriptPage from "../TranscriptPage"

vi.mock("@/context/useAuth", () => ({ useAuth: () => ({ user: { full_name: "Fallback Name" } }) }))

const cert = (over: Partial<Certificate>): Certificate =>
  ({ id: over.certificate_number, status: "approved", student_name: "Anna Petrenko", school_name: null, ...over }) as Certificate

describe("TranscriptPage", () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it("lists issued certificates oldest first, and leaves out the rest", async () => {
    vi.spyOn(coursesService, "getMyCertificates").mockResolvedValue([
      cert({ certificate_number: "EQ-2", course_title: "Romans", issued_at: "2026-06-01T10:00:00Z" }),
      cert({ certificate_number: "EQ-1", course_title: "Acts", issued_at: "2026-03-01T10:00:00Z", school_name: "Kyiv Bible School" }),
      cert({ certificate_number: "EQ-3", course_title: "Psalms", status: "pending", issued_at: null }),
    ])
    render(
      <I18nextProvider i18n={i18n}>
        <MemoryRouter>
          <TranscriptPage />
        </MemoryRouter>
      </I18nextProvider>,
    )
    expect(await screen.findByRole("heading", { name: "Anna Petrenko" })).toBeInTheDocument()
    const rows = screen.getAllByRole("row").slice(1)
    expect(rows.map((r) => r.textContent)).toEqual([
      expect.stringContaining("ActsKyiv Bible School"),
      expect.stringContaining("RomansEquip"),
    ])
    expect(screen.queryByText("Psalms")).toBeNull()
  })
})
