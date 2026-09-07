/**
 * An error message is text a person reads, and it was English for everyone.
 *
 * The server's ``message`` is written for a log: English prose, specific,
 * and produced without any idea who is reading. It went straight into the
 * toast, so a German student who ran out of quiz attempts was told so in
 * English on a page that was otherwise entirely German — and a Russian
 * teacher whose Wi-Fi dropped read "Network Error".
 *
 * The structured envelope carries a ``code``, and a code can be translated
 * where free prose cannot. These pin the order: the code's own sentence
 * first; no answer at all is «нет связи»; a 422 is rendered per field from
 * its identifiers; the server's raw words only in a dev build; then the
 * status's sentence; then the caller's fallback. Nothing English reaches a
 * production screen.
 */

import { AxiosError } from "axios"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

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

/** What axios throws when the request never got an answer. */
function networkError(): AxiosError {
  return new AxiosError("Network Error", AxiosError.ERR_NETWORK)
}

const LATIN_WORD = /(?<!\p{L})(Error|Network|Bands|Input|should|failed)(?!\p{L})/u

describe("the language an error is read in", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("de")
  })
  afterEach(() => {
    vi.unstubAllEnvs()
  })

  it("says it in the reader's language when the code is one we know", () => {
    const err = axiosError(409, {
      code: "quiz.attempts_exhausted",
      message: "No attempts remaining for this quiz",
    })

    expect(getErrorDetail(err)).toBe("Sie haben alle Versuche aufgebraucht.")
  })

  it("puts the envelope's number into the sentence", async () => {
    await i18n.changeLanguage("ru")
    const err = axiosError(409, {
      code: "quiz.has_attempts",
      message: "This quiz has 3 attempt(s)",
      context: { attempt_count: 3 },
    })

    expect(getErrorDetail(err)).toBe(
      "У этого теста уже 3 попытки. Удалить его — значит удалить их все вместе с оценками.",
    )
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

  describe("in production", () => {
    beforeEach(async () => {
      vi.stubEnv("DEV", false)
      await i18n.changeLanguage("ru")
    })

    it("says «нет связи» when the request never got an answer", () => {
      expect(getErrorDetail(networkError())).toBe("Нет связи. Проверьте интернет и повторите.")
    })

    it("does not pass a plain Error's message on — it is English by construction", () => {
      const message = getErrorDetail(new Error("timeout of 10000ms exceeded"), "Не удалось сохранить тест")
      expect(message).toBe("Не удалось сохранить тест")
    })

    it("uses the generic sentence for a plain Error when the caller gave no fallback", () => {
      expect(getErrorDetail(new Error("Network Error"))).toBe("Что-то пошло не так.")
    })

    it("does not show the server's words for a code we have no sentence for", () => {
      const err = axiosError(400, {
        code: "some.code.we.never.declared",
        message: "Bands must be an object keyed by scheme",
      })

      const message = getErrorDetail(err)
      expect(message).toBe("Запрос не принят. Проверьте введённые данные.")
      expect(message).not.toMatch(LATIN_WORD)
    })

    it("does not show a legacy string detail either", () => {
      expect(getErrorDetail(axiosError(404, "Course 'abc' not found"))).toBe("Не удалось это найти.")
    })

    it("tells the teacher a 413 means the block is too large", () => {
      expect(getErrorDetail(axiosError(413, "Request Entity Too Large"))).toBe(
        "Слишком большой блок — разбейте его на несколько.",
      )
    })

    it("renders a 422 per field, naming the question, not pydantic's English", () => {
      const err = axiosError(422, [
        {
          type: "less_than_equal",
          loc: ["body", "questions", 1, "points"],
          msg: "Input should be less than or equal to 100",
          input: 150,
          ctx: { le: 100 },
        },
      ])

      const message = getErrorDetail(err)
      expect(message).toBe("Вопрос 2, баллы: не больше 100")
      expect(message).not.toMatch(LATIN_WORD)
    })
  })

  describe("in a dev build", () => {
    beforeEach(async () => {
      vi.stubEnv("DEV", true)
      await i18n.changeLanguage("ru")
    })

    it("keeps the server's own words for a code we have no sentence for — someone is debugging", () => {
      const err = axiosError(400, {
        code: "some.code.we.never.declared",
        message: "Bands must be an object keyed by scheme",
      })

      expect(getErrorDetail(err)).toBe("Bands must be an object keyed by scheme")
    })

    it("still says «нет связи» — there are no server words to show", () => {
      expect(getErrorDetail(networkError())).toBe("Нет связи. Проверьте интернет и повторите.")
    })
  })
})
