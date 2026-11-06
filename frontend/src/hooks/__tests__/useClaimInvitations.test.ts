import { renderHook, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

import type { User } from "@/types"

const claimInvitations = vi.fn()
vi.mock("@/services/invitations", () => ({
  invitationsService: { claimInvitations: () => claimInvitations() },
}))

const refreshUser = vi.fn()
let currentUser: User | null = null
vi.mock("@/context/useAuth", () => ({ useAuth: () => ({ user: currentUser, refreshUser }) }))

const toast = vi.fn()
vi.mock("@/lib/toast", () => ({ toast: (o: unknown) => toast(o) }))

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string, o?: Record<string, string>) => `${key}:${o?.organization ?? ""}` }),
}))

import { useClaimInvitations } from "../useClaimInvitations"

const person = { id: "u1", email: "a@b.com", role: "student" } as unknown as User

/**
 * A person who came to the site without the invitation link still gets what
 * it offered: the app asks the server once a session (2026-11-06: every
 * teacher invited in October had signed up on their own and stayed a student).
 */
describe("claiming invitations on sign-in", () => {
  beforeEach(() => {
    claimInvitations.mockReset()
    refreshUser.mockReset()
    toast.mockReset()
    currentUser = person
  })

  it("asks once per person, and quietly when there was nothing", async () => {
    claimInvitations.mockResolvedValue([])
    const { rerender } = renderHook(() => useClaimInvitations(true))
    currentUser = { ...person, full_name: "A." } as User
    rerender()

    await waitFor(() => expect(claimInvitations).toHaveBeenCalledTimes(1))
    expect(refreshUser).not.toHaveBeenCalled()
    expect(toast).not.toHaveBeenCalled()
  })

  it("reloads the profile and says where the person now teaches", async () => {
    claimInvitations.mockResolvedValue([
      { role: "teacher", scope: "organization", enrolled_course_id: null, email: "a@b.com", organization_name: "UCOAT" },
    ])
    renderHook(() => useClaimInvitations(true))

    await waitFor(() => expect(refreshUser).toHaveBeenCalledTimes(1))
    expect(toast).toHaveBeenCalledWith({ variant: "success", title: "invite.claimed.teach:UCOAT" })
  })

  it("leaves the auth pages to the link", () => {
    renderHook(() => useClaimInvitations(false))
    expect(claimInvitations).not.toHaveBeenCalled()
  })

  it("does nothing for nobody, or for a closed account", () => {
    currentUser = null
    renderHook(() => useClaimInvitations(true))
    currentUser = { ...person, deleted_at: "2026-11-01T00:00:00Z" } as User
    renderHook(() => useClaimInvitations(true))
    expect(claimInvitations).not.toHaveBeenCalled()
  })
})
