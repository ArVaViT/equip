/**
 * An error message is text a person reads, and it was English for everyone.
 *
 * The server's ``message`` is written for a log: English prose, specific,
 * and produced without any idea who is reading. It went straight into the
 * toast, so a German student who ran out of quiz attempts was told so in
 * English on a page that was otherwise entirely German.
 *
 * The structured envelope carries a ``code``, and a code can be translated
 * where free prose cannot. These pin the order: the code's own sentence
 * first, the server's message when we have no sentence for that code, and
 * the status's sentence when there is no envelope at all.
 */

import { AxiosError } from "axios"
import { beforeEach, describe, expect, it } from "vitest"

import i18n from "@/i18n/config"
import { getErrorDetail } from "@/lib/errorDetail"

function axiosError(status: number, detail?: unknown): AxiosError {
  const err = new AxiosError("request failed")
  err.response = {
    status,
    statusText: "",
    headers: {},
    config: { headers: undefined } as never,
    data: detail === undefined ? {} : { detail },
  }
  return err
}

describe("the language an error is read in", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("de")
  })

  it("says it in the reader's language when the code is one we know", () => {
    const err = axiosError(409, {
      code: "quiz.attempts_exhausted",
      message: "No attempts remaining for this quiz",
    })

    expect(getErrorDetail(err)).toBe("Sie haben alle Versuche aufgebraucht.")
  })

  it("keeps the server's own words when we have no sentence for that code", () => {
    // Specific beats generic: better an English sentence naming the thing
    // than a translated sentence that says nothing.
    const err = axiosError(400, {
      code: "some.code.we.never.declared",
      message: "Bands must be an object keyed by scheme",
    })

    expect(getErrorDetail(err)).toBe("Bands must be an object keyed by scheme")
  })

  it("falls back to the status, translated, when there is no envelope", () => {
    expect(getErrorDetail(axiosError(500))).toBe("Serverfehler. Bitte später erneut versuchen.")
    expect(getErrorDetail(axiosError(403))).toBe("Sie haben dafür keine Berechtigung.")
  })

  it("has something to say about an error that is not an HTTP one", () => {
    expect(getErrorDetail({})).toBe("Etwas ist schiefgelaufen.")
  })

  it("follows the reader when they switch language", async () => {
    const err = axiosError(409, { code: "quiz.attempts_exhausted", message: "No attempts remaining" })
    await i18n.changeLanguage("uk")

    expect(getErrorDetail(err)).toBe("Спроби вичерпано.")
  })
})
