/**
 * The invite page, situation by situation — and none of them waits on email.
 *
 * Until 2026-10-15 the page signed an invited person up through Supabase and
 * then sat on «check your email»: a dead end on a slow inbox, a spam folder,
 * or a phone that opened the confirmation in another browser. Every person
 * stuck at sign-up in that period had come by invitation. The link already
 * proves the address, so the page now creates the account itself, signs in
 * and goes where the invitation leads; and a signed-in invitee is accepted
 * on arrival instead of being shown one more button.
 */
import { useEffect, type ReactNode } from "react"
import { AxiosError, AxiosHeaders } from "axios"
import { act, renderHook, waitFor } from "@testing-library/react"
import { MemoryRouter, useLocation } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { resetAcceptInviteForTests, useAcceptInvite } from "../useAcceptInvite"

const previewInvitation = vi.fn()
const acceptInvitation = vi.fn()
const registerByInvitation = vi.fn()
const login = vi.fn()
const signInWithGoogle = vi.fn()
const refreshUser = vi.fn()
let currentUser: { email: string } | null = null

vi.mock("@/services/invitations", () => ({
  invitationsService: {
    previewInvitation: (...args: unknown[]) => previewInvitation(...args),
    acceptInvitation: (...args: unknown[]) => acceptInvitation(...args),
    registerByInvitation: (...args: unknown[]) => registerByInvitation(...args),
  },
}))

vi.mock("@/context/useAuth", () => ({
  useAuth: () => ({ user: currentUser, login, signInWithGoogle, logout: vi.fn(), refreshUser }),
}))

const PREVIEW = {
  email: "sasha@web.de",
  role: "student",
  scope: "course",
  course_title: "Деяния",
  organization_name: "UCOAT",
  status: "pending",
  is_expired: false,
  unusable_reason: null,
  has_account: false,
}

const ACCEPTED = { role: "student", scope: "course", enrolled_course_id: "acts-1", email: "sasha@web.de" }

function refusal(status: number, code: string) {
  return new AxiosError("refused", String(status), undefined, undefined, {
    status,
    statusText: "",
    headers: {},
    config: { headers: new AxiosHeaders() },
    data: { detail: { code, message: "", context: {} } },
  })
}

let where = ""
function Probe() {
  const location = useLocation()
  useEffect(() => {
    where = `${location.pathname}${location.hash}`
  }, [location])
  return null
}

function wrapper({ children }: { children: ReactNode }) {
  return (
    <MemoryRouter initialEntries={["/invite/accept#token=tok-1"]}>
      {children}
      <Probe />
    </MemoryRouter>
  )
}

function fillForm(result: { current: ReturnType<typeof useAcceptInvite> }) {
  act(() => {
    result.current.handleChange("full_name", "Sasha Petrov")
    result.current.handleChange("password", "a long enough passphrase")
    result.current.handleChange("confirmPassword", "a long enough passphrase")
  })
}

describe("the invite page", () => {
  beforeEach(() => {
    for (const mock of [previewInvitation, acceptInvitation, registerByInvitation, login, signInWithGoogle, refreshUser]) {
      mock.mockReset()
    }
    currentUser = null
    resetAcceptInviteForTests()
    window.sessionStorage.clear()
    window.localStorage.clear()
  })

  it("offers a form when the address has no account", async () => {
    previewInvitation.mockResolvedValue(PREVIEW)
    const { result } = renderHook(() => useAcceptInvite(), { wrapper })
    await waitFor(() => expect(result.current.phase).toBe("form"))
  })

  it("asks to sign in, not to sign up, when the address has an account", async () => {
    previewInvitation.mockResolvedValue({ ...PREVIEW, has_account: true })
    const { result } = renderHook(() => useAcceptInvite(), { wrapper })
    await waitFor(() => expect(result.current.phase).toBe("signIn"))
    expect(result.current.invitePath).toBe("/invite/accept#token=tok-1")
  })

  it("creates the account, signs in with it and goes to the course — no email in between", async () => {
    previewInvitation.mockResolvedValue(PREVIEW)
    registerByInvitation.mockResolvedValue(ACCEPTED)
    login.mockResolvedValue(undefined)
    const { result, rerender } = renderHook(() => useAcceptInvite(), { wrapper })
    await waitFor(() => expect(result.current.phase).toBe("form"))
    fillForm(result)

    await act(() => result.current.handleSubmit())

    expect(registerByInvitation).toHaveBeenCalledWith("tok-1", "Sasha Petrov", "a long enough passphrase", "en")
    expect(login).toHaveBeenCalledWith("sasha@web.de", "a long enough passphrase")
    // The new session loads; the page is not asked to accept a second time.
    currentUser = { email: "sasha@web.de" }
    rerender()
    await waitFor(() => expect(where).toBe("/courses/acts-1"))
    expect(acceptInvitation).not.toHaveBeenCalled()
  })

  it("turns into sign-in when the server finds a confirmed account after all", async () => {
    previewInvitation.mockResolvedValue(PREVIEW)
    registerByInvitation.mockRejectedValue(refusal(409, "invitation.account_exists"))
    const { result } = renderHook(() => useAcceptInvite(), { wrapper })
    await waitFor(() => expect(result.current.phase).toBe("form"))
    fillForm(result)

    await act(() => result.current.handleSubmit())

    expect(result.current.phase).toBe("signIn")
    expect(login).not.toHaveBeenCalled()
  })

  it("puts a breached password on the password field", async () => {
    previewInvitation.mockResolvedValue(PREVIEW)
    registerByInvitation.mockRejectedValue(refusal(422, "auth.weak_password"))
    const { result } = renderHook(() => useAcceptInvite(), { wrapper })
    await waitFor(() => expect(result.current.phase).toBe("form"))
    fillForm(result)

    await act(() => result.current.handleSubmit())

    expect(result.current.errors.password).toBeTruthy()
    expect(result.current.phase).toBe("form")
  })

  it("accepts on arrival for the invitee signed in under any case of the address", async () => {
    currentUser = { email: "Sasha@Web.de" }
    previewInvitation.mockResolvedValue(PREVIEW)
    acceptInvitation.mockResolvedValue(ACCEPTED)
    renderHook(() => useAcceptInvite(), { wrapper })

    await waitFor(() => expect(where).toBe("/courses/acts-1"))
    expect(acceptInvitation).toHaveBeenCalledTimes(1)
    expect(refreshUser).toHaveBeenCalled()
  })

  it("goes home after accepting an invitation to the school", async () => {
    currentUser = { email: "sasha@web.de" }
    previewInvitation.mockResolvedValue({ ...PREVIEW, scope: "organization", course_title: null })
    acceptInvitation.mockResolvedValue({ ...ACCEPTED, scope: "organization", enrolled_course_id: null })
    renderHook(() => useAcceptInvite(), { wrapper })
    await waitFor(() => expect(where).toBe("/"))
  })

  it("does not accept for somebody signed in under another address", async () => {
    currentUser = { email: "someone@else.org" }
    previewInvitation.mockResolvedValue(PREVIEW)
    const { result } = renderHook(() => useAcceptInvite(), { wrapper })
    await waitFor(() => expect(result.current.phase).toBe("mismatch"))
    expect(acceptInvitation).not.toHaveBeenCalled()
  })

  it("names the refusal it meets while accepting", async () => {
    currentUser = { email: "sasha@web.de" }
    previewInvitation.mockResolvedValue(PREVIEW)
    acceptInvitation.mockRejectedValue(refusal(403, "invitation.inviter_not_staff"))
    const { result } = renderHook(() => useAcceptInvite(), { wrapper })
    await waitFor(() => expect(result.current.phase).toBe("unusable"))
    expect(result.current.reason).toBe("inviter_left")
  })

  it.each(["expired", "used", "revoked", "inviter_left", "course_gone"] as const)(
    "names why a spent link is spent: %s",
    async (reason) => {
      previewInvitation.mockResolvedValue({ ...PREVIEW, unusable_reason: reason })
      const { result } = renderHook(() => useAcceptInvite(), { wrapper })
      await waitFor(() => expect(result.current.phase).toBe("unusable"))
      expect(result.current.reason).toBe(reason)
    },
  )

  it("keeps a fulfilled invitation open for its invitee", async () => {
    previewInvitation.mockResolvedValue({ ...PREVIEW, status: "fulfilled" })
    const { result } = renderHook(() => useAcceptInvite(), { wrapper })
    await waitFor(() => expect(result.current.phase).toBe("form"))
  })

  it("keeps the way back from Google in this tab only, never browser-wide", async () => {
    previewInvitation.mockResolvedValue(PREVIEW)
    signInWithGoogle.mockReturnValue(new Promise(() => undefined))
    const { result } = renderHook(() => useAcceptInvite(), { wrapper })
    await waitFor(() => expect(result.current.phase).toBe("form"))

    act(() => void result.current.handleGoogle())

    expect(window.sessionStorage.getItem("equip:returnTo")).toBe("/invite/accept#token=tok-1")
    expect(JSON.stringify({ ...window.localStorage })).not.toContain("tok-1")
  })
})
