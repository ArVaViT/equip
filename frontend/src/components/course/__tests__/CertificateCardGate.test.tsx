import type { ReactNode } from "react"
import { render, screen } from "@testing-library/react"
import { I18nextProvider } from "react-i18next"
import { MemoryRouter } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"
import i18n from "@/i18n/config"
import CertificateCard from "../CertificateCard"

vi.mock("@/context/useAuth", () => ({ useAuth: () => ({ user: { id: "s-1", full_name: "Пётр" } }) }))

function Wrapper({ children }: { children: ReactNode }) {
  return (
    <I18nextProvider i18n={i18n}>
      <MemoryRouter>{children}</MemoryRouter>
    </I18nextProvider>
  )
}

function show({ blocked }: { blocked: boolean }) {
  return render(
    <CertificateCard
      courseId="c-1"
      progress={100}
      blocked={blocked}
      certificate={null}
      onCertificateUpdate={vi.fn()}
    />,
    { wrapper: Wrapper },
  )
}

describe("CertificateCard — the gate (D9)", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru")
  })

  it("offers the certificate when nothing stands in the way", () => {
    show({ blocked: false })

    expect(screen.getByRole("button")).toBeInTheDocument()
  })

  it("points at the reasons instead of offering a button that can only fail", () => {
    show({ blocked: true })

    // The server refuses with the same list the grade card above is already
    // showing, with links to the actual work. A button here would be a button
    // whose only possible outcome is an error toast — and repeating the list
    // in two places is how the two copies drift apart.
    expect(screen.queryByRole("button")).not.toBeInTheDocument()
    expect(screen.getByText(/когда закроются пункты выше/)).toBeInTheDocument()
  })
})
