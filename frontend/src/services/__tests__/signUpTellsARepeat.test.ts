/**
 * Signing up again with an address nobody confirmed.
 *
 * GoTrue mails a fresh link and keeps everything else about the account —
 * the password of the first attempt included — and answers with that older
 * account. The register screen has to know, or it tells the person to sign
 * in with a password that does not work.
 */
import { beforeEach, describe, expect, it, vi } from "vitest"

const signUp = vi.fn()
vi.mock("@/lib/supabase", () => ({ supabase: { auth: { signUp: (a: unknown) => signUp(a) } } }))

import { authService } from "@/services/auth"

function answer(createdAt: string, sentAt: string) {
  signUp.mockResolvedValue({
    data: { user: { id: "u1", identities: [{}], created_at: createdAt, confirmation_sent_at: sentAt } },
    error: null,
  })
}

describe("authService.register", () => {
  beforeEach(() => signUp.mockReset())

  it("calls a brand-new account new", async () => {
    answer("2026-10-15T20:00:00.000Z", "2026-10-15T20:00:00.120Z")
    expect(await authService.register("a@b.de", "a long enough pass", "A", "de")).toEqual({
      userId: "u1",
      repeated: false,
    })
  })

  it("recognises the older account GoTrue answers a repeat with", async () => {
    answer("2026-10-14T09:00:00.000Z", "2026-10-15T20:00:00.000Z")
    expect((await authService.register("a@b.de", "a long enough pass", "A", "de")).repeated).toBe(true)
  })
})
