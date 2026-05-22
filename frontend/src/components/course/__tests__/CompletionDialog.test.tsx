import type { ReactNode } from "react"
import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { I18nextProvider } from "react-i18next"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import i18n from "@/i18n/config"
import CompletionDialog from "../CompletionDialog"
import type { Certificate } from "@/types"

const requestCertificateMock = vi.fn<(courseId: string) => Promise<Certificate>>()

vi.mock("@/services/courses", () => ({
  coursesService: {
    requestCertificate: (...args: [string]) => requestCertificateMock(...args),
  },
}))

vi.mock("@/lib/toast", () => ({
  toast: vi.fn(),
}))

function Wrapper({ children }: { children: ReactNode }) {
  return <I18nextProvider i18n={i18n}>{children}</I18nextProvider>
}

const baseProps = {
  open: true,
  onClose: vi.fn(),
  courseId: "course-1",
  courseTitle: "Romans for Beginners",
  hasCertificate: false,
  onCertificateRequested: vi.fn(),
}

beforeEach(() => {
  requestCertificateMock.mockReset()
  baseProps.onClose = vi.fn()
  baseProps.onCertificateRequested = vi.fn()
})

afterEach(() => {
  vi.clearAllMocks()
})

describe("CompletionDialog", () => {
  it("does not render anything when closed", () => {
    render(<CompletionDialog {...baseProps} open={false} />, { wrapper: Wrapper })
    expect(screen.queryByText(/romans for beginners/i)).not.toBeInTheDocument()
  })

  it("renders the editorial composition with the course title in the heading", () => {
    render(<CompletionDialog {...baseProps} />, { wrapper: Wrapper })
    // Editorial composition lands a real <h2>-level dialog title via
    // Radix, so screen readers + tests can both find it by role.
    expect(
      screen.getByRole("heading", { name: /romans for beginners/i }),
    ).toBeInTheDocument()
  })

  it("offers the Request CTA when no certificate exists yet", () => {
    render(<CompletionDialog {...baseProps} hasCertificate={false} />, {
      wrapper: Wrapper,
    })
    expect(
      screen.getByRole("button", { name: i18n.t("completion.requestCta") }),
    ).toBeInTheDocument()
  })

  it("hides the Request CTA once a certificate is already on file", () => {
    render(<CompletionDialog {...baseProps} hasCertificate={true} />, {
      wrapper: Wrapper,
    })
    expect(
      screen.queryByRole("button", { name: i18n.t("completion.requestCta") }),
    ).not.toBeInTheDocument()
    // Continue is always available so the user can close from the body
    expect(
      screen.getByRole("button", { name: i18n.t("completion.continueCta") }),
    ).toBeInTheDocument()
  })

  it("requests the certificate, notifies parent, then closes on success", async () => {
    const cert: Certificate = {
      id: "cert-1",
      user_id: "u-1",
      course_id: "course-1",
      archived_course_title: null,
      issued_at: null,
      certificate_number: null,
      status: "pending",
      requested_at: "2026-05-20T00:00:00Z",
      teacher_approved_at: null,
      teacher_approved_by: null,
      admin_approved_at: null,
      admin_approved_by: null,
    }
    requestCertificateMock.mockResolvedValueOnce(cert)
    const onClose = vi.fn()
    const onCertificateRequested = vi.fn()

    render(
      <CompletionDialog
        {...baseProps}
        onClose={onClose}
        onCertificateRequested={onCertificateRequested}
      />,
      { wrapper: Wrapper },
    )

    fireEvent.click(
      screen.getByRole("button", { name: i18n.t("completion.requestCta") }),
    )

    await waitFor(() => {
      expect(requestCertificateMock).toHaveBeenCalledWith("course-1")
    })
    await waitFor(() => {
      expect(onCertificateRequested).toHaveBeenCalledWith(cert)
    })
    await waitFor(() => {
      expect(onClose).toHaveBeenCalled()
    })
  })
})
