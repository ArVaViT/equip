/**
 * The accept page when the account holds more in another school.
 *
 * The server refuses such an acceptance (`invitation.other_school`): it would
 * either carry a director's or teacher's role into this school or quietly take
 * it away. The page says which of those it is instead of «try again».
 */
import type { ReactNode } from "react"
import { act, renderHook, waitFor } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { AxiosError } from "axios"
import { describe, expect, it, vi } from "vitest"

import i18n from "@/i18n/config"
import { useAcceptInvite } from "../useAcceptInvite"

const refused = new AxiosError("conflict", "ERR_BAD_REQUEST")
Object.assign(refused, {
  response: { status: 409, data: { detail: { code: "invitation.other_school", message: "x" } } },
})

vi.mock("@/services/invitations", () => ({
  invitationsService: {
    previewInvitation: vi.fn().mockResolvedValue({
      email: "teacher@example.com",
      role: "student",
      scope: "course",
      course_title: null,
      is_expired: false,
      status: "pending",
    }),
    acceptInvitation: vi.fn(() => Promise.reject(refused)),
  },
}))

vi.mock("@/context/useAuth", () => ({
  useAuth: () => ({
    user: { email: "teacher@example.com" },
    register: vi.fn(),
    signInWithGoogle: vi.fn(),
    logout: vi.fn(),
    refreshUser: vi.fn(),
  }),
}))

function wrapper({ children }: { children: ReactNode }) {
  return <MemoryRouter initialEntries={["/invite/accept?token=tok-1"]}>{children}</MemoryRouter>
}

describe("useAcceptInvite refused for another school", () => {
  it("says why, not «try again»", async () => {
    await i18n.changeLanguage("en")
    const { result } = renderHook(() => useAcceptInvite(), { wrapper })
    await waitFor(() => expect(result.current.phase).toBe("ready"))

    await act(() => result.current.acceptNow())

    expect(result.current.serverError).toBe(i18n.t("invite.errors.otherSchool"))
  })
})
