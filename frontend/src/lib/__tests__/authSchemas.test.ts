/**
 * The form's rules against the server's rules.
 *
 * These schemas asked for six characters while Supabase Auth was configured
 * to demand twelve, so the form's own verdict was worthless: it passed
 * passwords the server then refused, and the refusal arrived as prose after
 * submit. The point of these tests is that the two can never drift apart
 * silently again.
 */
import { describe, expect, it } from "vitest"
import {
  makeAcceptInviteSchema,
  makeLoginSchema,
  makeRegisterSchema,
} from "@/lib/validations/auth"
import { PASSWORD_MIN_LENGTH } from "@/lib/passwordPolicy"

const TOO_SHORT = "a".repeat(PASSWORD_MIN_LENGTH - 1)
const LONG_ENOUGH = "a".repeat(PASSWORD_MIN_LENGTH)

describe("makeRegisterSchema", () => {
  it("refuses one character below the server's minimum", () => {
    const result = makeRegisterSchema().safeParse({
      full_name: "Vadym Arnaut",
      email: "someone@example.com",
      password: TOO_SHORT,
      confirmPassword: TOO_SHORT,
    })
    expect(result.success).toBe(false)
  })

  it("accepts exactly the server's minimum", () => {
    const result = makeRegisterSchema().safeParse({
      full_name: "Vadym Arnaut",
      email: "someone@example.com",
      password: LONG_ENOUGH,
      confirmPassword: LONG_ENOUGH,
    })
    expect(result.success).toBe(true)
  })

  it("names the number in the message rather than leaving it to be guessed", () => {
    const result = makeRegisterSchema().safeParse({
      full_name: "Vadym Arnaut",
      email: "someone@example.com",
      password: TOO_SHORT,
      confirmPassword: TOO_SHORT,
    })
    expect(result.success).toBe(false)
    if (result.success) return
    const message = result.error.issues.map((issue) => issue.message).join(" ")
    expect(message).toContain(String(PASSWORD_MIN_LENGTH))
  })
})

describe("makeAcceptInviteSchema", () => {
  it("holds an invited teacher to the same minimum", () => {
    expect(
      makeAcceptInviteSchema().safeParse({
        full_name: "Dmytro Kostantynov",
        password: TOO_SHORT,
        confirmPassword: TOO_SHORT,
      }).success,
    ).toBe(false)
  })
})

describe("makeLoginSchema", () => {
  it("does not hold an existing password to today's minimum", () => {
    // Accounts created before `password_min_length` was raised still have
    // shorter passwords. Refusing them here would lock people out of the
    // product over a rule that only governs new passwords.
    expect(
      makeLoginSchema().safeParse({ email: "someone@example.com", password: "old-one" }).success,
    ).toBe(true)
  })

  it("still requires something to be typed", () => {
    expect(
      makeLoginSchema().safeParse({ email: "someone@example.com", password: "" }).success,
    ).toBe(false)
  })
})
