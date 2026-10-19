import type { ReactNode } from "react"
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { I18nextProvider } from "react-i18next"
import { MemoryRouter } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"
import i18n from "@/i18n/config"
import { coursesService } from "@/services/courses"
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

  it("does the same after a refusal: no re-request while something still stands", () => {
    render(
      <CertificateCard
        courseId="c-1"
        progress={100}
        blocked
        certificate={{ id: "cert-1", status: "rejected", course_id: "c-1" } as never}
        onCertificateUpdate={vi.fn()}
      />,
      { wrapper: Wrapper },
    )

    expect(screen.queryByRole("button")).not.toBeInTheDocument()
    expect(screen.getByText(/когда закроются пункты выше/)).toBeInTheDocument()
  })

  it("does not offer a request over a certificate it could not look up", async () => {
    const onUpdate = vi.fn()
    const lookup = vi.spyOn(coursesService, "getCourseCertificate").mockResolvedValue({
      id: "cert-1",
      status: "approved",
      certificate_number: "EQ-1",
    } as never)
    render(
      <CertificateCard courseId="c-1" progress={100} certificate={undefined} onCertificateUpdate={onUpdate} />,
      { wrapper: Wrapper },
    )

    // A failed read used to render as «no certificate yet» — with a button
    // whose only outcome, for a student who already holds one, is a refusal.
    expect(screen.queryByRole("button", { name: /Запросить/ })).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole("button", { name: "Повторить" }))
    await waitFor(() => expect(onUpdate).toHaveBeenCalledWith(expect.objectContaining({ id: "cert-1" })))
    expect(lookup).toHaveBeenCalledWith("c-1")
  })
})
