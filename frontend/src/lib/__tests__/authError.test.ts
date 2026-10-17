/**
 * The sign-in screen must never speak English to a German.
 *
 * `setServerError(supaErr.message || t(...))` looked like it had a
 * translated fallback. GoTrue always sends a `message`, so it never ran —
 * "Invalid login credentials" and "User already registered" went straight
 * onto the first screen the product shows anyone.
 */

import { afterAll, afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import i18n, { SUPPORTED_LOCALES } from "@/i18n/config"
import { authErrorMessage, emailSendErrorMessage, isDuplicateEmail } from "../authError"

/** What supabase-js throws: an Error subclass carrying `status` + `code`. */
function goTrueError(message: string, extra: { status?: number; code?: string } = {}) {
  return Object.assign(new Error(message), extra)
}

beforeEach(() => {
  // The helper logs the raw server text in dev; keep it out of the report.
  vi.spyOn(console, "error").mockImplementation(() => {})
})

afterEach(() => {
  vi.restoreAllMocks()
})

afterAll(async () => {
  await i18n.changeLanguage("en")
})

describe("authErrorMessage", () => {
  it("never returns the server's own words", () => {
    const raw = "Invalid login credentials"
    expect(authErrorMessage(goTrueError(raw, { status: 400, code: "invalid_credentials" }), "auth.loginFailed")).not.toBe(raw)
  })

  it("tells a wrong password apart from too many attempts", () => {
    // The reason this branches on `code` at all: one of these means "check
    // what you typed" and the other means "stop typing and wait", and a
    // reader told the wrong one retypes a password that was fine.
    const wrongPassword = authErrorMessage(
      goTrueError("Invalid login credentials", { status: 400, code: "invalid_credentials" }),
      "auth.loginFailed",
    )
    const rateLimited = authErrorMessage(
      goTrueError("Request rate limit reached", { status: 429, code: "over_request_rate_limit" }),
      "auth.loginFailed",
    )
    expect(wrongPassword).toBe(i18n.t("auth.errors.invalidCredentials"))
    expect(rateLimited).toBe(i18n.t("auth.errors.rateLimited"))
    expect(wrongPassword).not.toBe(rateLimited)
  })

  it("reads the status when the response carries no code", () => {
    // GoTrue only started sending `code` reliably in 2.x; a lagging or
    // self-hosted project still answers without one.
    expect(authErrorMessage(goTrueError("Too many requests", { status: 429 }), "auth.loginFailed")).toBe(
      i18n.t("auth.errors.rateLimited"),
    )
    expect(authErrorMessage(goTrueError("boom", { status: 503 }), "auth.loginFailed")).toBe(
      i18n.t("auth.errors.serverError"),
    )
  })

  it("falls back to the screen's own sentence for anything unrecognised", () => {
    expect(authErrorMessage(goTrueError("who knows", { status: 400 }), "auth.loginFailed")).toBe(
      i18n.t("auth.loginFailed"),
    )
    expect(authErrorMessage(undefined, "auth.errors.registrationFailed")).toBe(
      i18n.t("auth.errors.registrationFailed"),
    )
    expect(authErrorMessage("a bare string", "auth.loginFailed")).toBe(i18n.t("auth.loginFailed"))
  })

  it("answers in the language on screen, in every language served", async () => {
    const err = goTrueError("Invalid login credentials", { status: 400, code: "invalid_credentials" })
    const seen = new Set<string>()
    for (const locale of SUPPORTED_LOCALES) {
      await i18n.changeLanguage(locale)
      const message = authErrorMessage(err, "auth.loginFailed")
      expect(message).toBe(i18n.t("auth.errors.invalidCredentials"))
      seen.add(message)
    }
    // Four distinct sentences — a shared string would satisfy every
    // assertion above while showing everybody English.
    expect(seen.size).toBe(SUPPORTED_LOCALES.length)
  })
})

describe("isDuplicateEmail", () => {
  it("recognises both shapes the stack produces", () => {
    // Our own sentinel, thrown when signUp returns an empty `identities`
    // array — Supabase's way of not confirming an address exists to an
    // unauthenticated caller.
    expect(isDuplicateEmail(new Error("DUPLICATE_EMAIL"))).toBe(true)
    // And the real error a project with email confirmation off returns.
    expect(isDuplicateEmail(goTrueError("User already registered", { code: "user_already_exists" }))).toBe(true)
  })

  it("does not swallow unrelated failures", () => {
    expect(isDuplicateEmail(goTrueError("Password is too weak", { code: "weak_password" }))).toBe(false)
    expect(isDuplicateEmail(null)).toBe(false)
  })
})

describe("the two email limits behind one code", () => {
  it("names the seconds when it is this address's one-a-minute limit", () => {
    const err = Object.assign(new Error("For security purposes, you can only request this after 42 seconds."), {
      code: "over_email_send_rate_limit",
      status: 429,
    })
    expect(authErrorMessage(err, "auth.loginFailed")).toBe(i18n.t("auth.errors.emailCooldown", { seconds: 42 }))
  })

  it("does not say «a minute» when it is the project's hourly allowance", () => {
    const err = Object.assign(new Error("email rate limit exceeded"), { code: "over_email_send_rate_limit", status: 429 })
    const message = authErrorMessage(err, "auth.loginFailed")
    expect(message).toBe(i18n.t("auth.errors.emailQuota"))
    expect(message).not.toMatch(/minute/i)
  })

  it("reads the send-email hook's five-minute refusal, which GoTrue relays as a bare 429", () => {
    // `supabase/functions/send-email/copy.ts::repeatRefusal`; no `code` survives the relay.
    const err = Object.assign(new Error("For security purposes, you can only request this after 240 seconds."), {
      status: 429,
    })
    expect(authErrorMessage(err, "auth.loginFailed")).toBe(i18n.t("auth.errors.emailCooldownMinutes", { minutes: 4 }))
  })

  it("rounds a wait over a minute up to whole minutes", () => {
    const err = Object.assign(new Error("For security purposes, you can only request this after 61 seconds."), {
      code: "over_email_send_rate_limit",
      status: 429,
    })
    expect(authErrorMessage(err, "auth.loginFailed")).toBe(i18n.t("auth.errors.emailCooldownMinutes", { minutes: 2 }))
  })

  it("leaves a 429 without the sentence to the generic «too many attempts»", () => {
    const err = Object.assign(new Error("Request rate limit reached"), { status: 429 })
    expect(authErrorMessage(err, "auth.loginFailed")).toBe(i18n.t("auth.errors.rateLimited"))
  })
})

describe("emailSendErrorMessage: every shape of a failed send says something a person can act on", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru")
  })

  it("reads the send-email hook's refusal exactly as GoTrue relays it: 429, code `unknown`", () => {
    // internal/hooks/hookserrors: {error:{http_code:429,message}} -> HTTPError
    // without an error code -> 2024-01-01 response {code:"unknown", message}.
    const err = goTrueError("For security purposes, you can only request this after 97 seconds.", {
      status: 429,
      code: "unknown",
    })
    const text = emailSendErrorMessage(err)
    expect(text).toBe(i18n.t("auth.errors.emailCooldownMinutes", { minutes: 2 }))
    expect(text).toContain("Спам")
  })

  it("names the spam folder under a minute too", () => {
    const err = goTrueError("For security purposes, you can only request this after 42 seconds.", {
      status: 429,
      code: "over_email_send_rate_limit",
    })
    expect(emailSendErrorMessage(err)).toContain("Спам")
    expect(emailSendErrorMessage(err)).toContain("42")
  })

  it("a 429 with words we do not know is still «already sent», not «server down»", () => {
    const err = goTrueError("Too many", { status: 429, code: "unknown" })
    expect(emailSendErrorMessage(err)).toBe(i18n.t("auth.errors.emailAlreadySent"))
  })

  it("too many requests from this connection is not «already sent»: nothing may have left", () => {
    const err = goTrueError("Request rate limit reached", { status: 429, code: "over_request_rate_limit" })
    expect(emailSendErrorMessage(err)).toBe(i18n.t("auth.errors.rateLimited"))
  })

  it("the project's hourly allowance is its own sentence", () => {
    const err = goTrueError("email rate limit exceeded", { status: 429, code: "over_email_send_rate_limit" })
    expect(emailSendErrorMessage(err)).toBe(i18n.t("auth.errors.emailQuota"))
  })

  it.each([
    ["a hook timeout", { status: 422, code: "hook_timeout_after_retry" }],
    ["a 500 from the hook", { status: 500, code: "unexpected_failure" }],
    ["a dropped connection", { status: 0 }],
    ["nothing at all", {}],
  ])("%s points at the earlier email and a retry", (_label, extra) => {
    const text = emailSendErrorMessage(goTrueError("Error sending magic link email", extra))
    expect(text).toBe(i18n.t("auth.errors.emailSendFailed"))
    expect(text).toContain("Спам")
    expect(text).not.toContain("Error sending")
  })

  it("has the sentences in every language", () => {
    for (const locale of SUPPORTED_LOCALES) {
      for (const key of ["auth.errors.emailSendFailed", "auth.errors.emailAlreadySent"]) {
        expect(i18n.exists(key, { lng: locale })).toBe(true)
      }
    }
  })
})
