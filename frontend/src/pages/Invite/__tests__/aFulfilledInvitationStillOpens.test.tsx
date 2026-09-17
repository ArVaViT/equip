/**
 * The accept page for an invitation whose person already arrived.
 *
 * The database marks an invitation `fulfilled` the moment its person gets what
 * it offered by another door — and for a platform invitation, signing up from
 * the link is that door, seconds before the person presses Accept. The page
 * used to treat anything that was not `pending` as spent, which would have
 * told exactly the invited person that their link no longer worked.
 */
import type { ReactNode } from "react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { renderHook, waitFor } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"

import { useAcceptInvite } from "../useAcceptInvite"

const previewInvitation = vi.fn()
let currentUser: { email: string } | null = null

vi.mock("@/services/invitations", () => ({
  invitationsService: {
    previewInvitation: (...args: unknown[]) => previewInvitation(...args),
    acceptInvitation: vi.fn(),
  },
}))

vi.mock("@/context/useAuth", () => ({
  useAuth: () => ({
    user: currentUser,
    register: vi.fn(),
    signInWithGoogle: vi.fn(),
    logout: vi.fn(),
    refreshUser: vi.fn(),
  }),
}))

const PREVIEW = {
  email: "arrived@example.com",
  role: "student",
  scope: "course",
  course_title: null,
  is_expired: false,
}

function wrapper({ children }: { children: ReactNode }) {
  return <MemoryRouter initialEntries={["/invite/accept?token=tok-1"]}>{children}</MemoryRouter>
}

describe("useAcceptInvite with a fulfilled invitation", () => {
  beforeEach(() => {
    previewInvitation.mockReset()
    currentUser = null
  })

  it("sends a signed-out visitor to sign in, not to a spent-link screen", async () => {
    previewInvitation.mockResolvedValue({ ...PREVIEW, status: "fulfilled" })
    const { result } = renderHook(() => useAcceptInvite(), { wrapper })
    await waitFor(() => expect(result.current.phase).toBe("alreadyIn"))
  })

  it("lets the invitee, signed in, accept it", async () => {
    currentUser = { email: "Arrived@Example.com" }
    previewInvitation.mockResolvedValue({ ...PREVIEW, status: "fulfilled" })
    const { result } = renderHook(() => useAcceptInvite(), { wrapper })
    await waitFor(() => expect(result.current.phase).toBe("ready"))
  })

  it("still refuses an expired one", async () => {
    previewInvitation.mockResolvedValue({ ...PREVIEW, status: "fulfilled", is_expired: true })
    const { result } = renderHook(() => useAcceptInvite(), { wrapper })
    await waitFor(() => expect(result.current.phase).toBe("unusable"))
  })

  it("still treats accepted and revoked as spent", async () => {
    for (const status of ["accepted", "revoked"]) {
      previewInvitation.mockResolvedValue({ ...PREVIEW, status })
      const { result, unmount } = renderHook(() => useAcceptInvite(), { wrapper })
      await waitFor(() => expect(result.current.phase).toBe("unusable"))
      unmount()
    }
  })
})
