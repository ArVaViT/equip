import { beforeEach, describe, expect, it, vi } from "vitest"

const signInWithOtp = vi.fn()
vi.mock("@/lib/supabase", () => ({
  supabase: { auth: { signInWithOtp: (...args: unknown[]) => signInWithOtp(...args) } },
}))

const { authService } = await import("@/services/auth")

/**
 * Signing in with a link must not quietly become a way to register.
 *
 * `signInWithOtp` creates the account by default. Left that way, a typo in
 * the address makes a second empty account and the person is signed into it,
 * wondering where their courses went — and the sign-in form becomes a
 * registration form nobody chose. The flag is the whole safeguard, and it is
 * one word in an options object, so it is worth a test of its own.
 */
describe("authService.sendSignInLink", () => {
  beforeEach(() => signInWithOtp.mockReset())

  it("never creates an account", async () => {
    signInWithOtp.mockResolvedValueOnce({ data: {}, error: null })

    await authService.sendSignInLink("reader@example.com")

    expect(signInWithOtp).toHaveBeenCalledWith(
      expect.objectContaining({
        email: "reader@example.com",
        options: expect.objectContaining({ shouldCreateUser: false }),
      }),
    )
  })

  it("sends the reader back to the page that can read the link", async () => {
    signInWithOtp.mockResolvedValueOnce({ data: {}, error: null })

    await authService.sendSignInLink("reader@example.com")

    const options = signInWithOtp.mock.calls[0]![0].options
    expect(options.emailRedirectTo).toMatch(/\/auth\/confirm$/)
  })

  it("passes the server's refusal on to the caller", async () => {
    signInWithOtp.mockResolvedValueOnce({ data: null, error: new Error("nope") })

    await expect(authService.sendSignInLink("reader@example.com")).rejects.toThrow("nope")
  })
})
