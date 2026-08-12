import type { ReactNode } from "react"
import { render, screen } from "@testing-library/react"
import { I18nextProvider } from "react-i18next"
import { beforeEach, describe, expect, it, vi } from "vitest"
import i18n from "@/i18n/config"
import { PendingCertsCard } from "../PendingCertsCard"
import type { PendingCert } from "../types"

function cert(over: Partial<PendingCert> = {}): PendingCert {
  return {
    id: "cert-1",
    user_id: "s-1",
    course_id: "c-1",
    status: "pending",
    requested_at: "2026-08-10T09:00:00Z",
    issued_at: null,
    certificate_number: null,
    student_name: "Пётр Иванов",
    course_title: "Послание к Римлянам",
    ...over,
  } as PendingCert
}

function Wrapper({ children }: { children: ReactNode }) {
  return <I18nextProvider i18n={i18n}>{children}</I18nextProvider>
}

function show(certs: PendingCert[]) {
  return render(
    <PendingCertsCard certs={certs} actionId={null} onApprove={vi.fn()} onReject={vi.fn()} />,
    { wrapper: Wrapper },
  )
}

describe("PendingCertsCard — what the reviewer is signing", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru")
  })

  it("warns when the request is not earned yet", () => {
    show([
      cert({
        blockers: [
          { code: "work_not_graded", params: { count: 2 }, chapter_ids: [] },
          { code: "below_threshold", params: { final_score: 40 }, chapter_ids: [] },
        ],
      }),
    ])

    // Approving is a signature on a document saying the course was passed. A
    // request raised before the gate existed arrives here looking exactly like
    // an earned one.
    expect(screen.getByText(/Ещё не заработан: 2/)).toBeInTheDocument()
  })

  it("says nothing on an earned request", () => {
    show([cert({ blockers: [] })])

    // A warning on every row is a warning nobody reads.
    expect(screen.queryByText(/Ещё не заработан/)).not.toBeInTheDocument()
  })

  it("says nothing when the field is absent altogether", () => {
    show([cert()])

    expect(screen.queryByText(/Ещё не заработан/)).not.toBeInTheDocument()
    expect(screen.getByText("Пётр Иванов")).toBeInTheDocument()
  })
})
