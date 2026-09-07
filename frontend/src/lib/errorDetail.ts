import { isAxiosError } from "axios"

import i18n from "@/i18n/config"
import { getErrorCode, getErrorContext } from "@/lib/errorCode"
import { describeValidationErrors, isValidationList } from "@/lib/validationErrors"

function safeStringify(value: unknown): string | null {
  // Pydantic validation errors arrive as arrays of `{loc, msg, type}`. Plain
  // JSON.stringify dumps them as raw JSON and exposes internals in toasts.
  // Try a few friendly shapes first, then fall back to JSON, and swallow
  // circular-reference errors so we never blow up on the error path itself.
  try {
    if (Array.isArray(value)) {
      const msgs = value
        .map((v) => (v && typeof v === "object" && "msg" in v ? String((v as { msg: unknown }).msg) : null))
        .filter((v): v is string => Boolean(v))
      if (msgs.length > 0) return msgs.join("; ")
    }
    if (value && typeof value === "object" && "msg" in value) {
      const msg = (value as { msg: unknown }).msg
      if (typeof msg === "string") return msg
    }
    return JSON.stringify(value)
  } catch {
    return null
  }
}

/**
 * The server's own words — English, written for a log — for whoever is
 * debugging. They never reach a production screen: a teacher with a
 * Russian interface was reading "Network Error" and "Bands must be an
 * object keyed by scheme" in toasts, and neither told her what to do.
 * Read at call time, not module load, so a test can flip it.
 */
function rawServerText(detail: unknown): string | null {
  if (!import.meta.env.DEV) return null
  if (typeof detail === "string") return detail
  if (
    detail &&
    typeof detail === "object" &&
    "message" in detail &&
    typeof (detail as { message: unknown }).message === "string"
  ) {
    return (detail as { message: string }).message
  }
  if (detail) return safeStringify(detail)
  return null
}

const STATUS_WITH_A_SENTENCE = new Set([400, 401, 403, 404, 409, 413, 422, 429])

/**
 * The message to show a person, in their own language.
 *
 * The server's ``message`` is English prose — it is written for a log and
 * for a developer reading a response — and it used to be returned straight
 * into a toast. A German student who ran out of quiz attempts was told so
 * in English, on a page that was otherwise entirely German; a Russian
 * teacher whose connection dropped read "Network Error".
 *
 * The order, best first:
 *
 * 1. The code's own sentence (``errors.byCode.*``), with the envelope's
 *    ``context`` available to it — so «в тесте уже 3 попытки» can say 3.
 * 2. No response at all (the request never got an answer): «Нет связи».
 * 3. A 422 list from pydantic, rendered per field in the reader's language
 *    — ``loc`` and ``type`` are identifiers, the English ``msg`` is not.
 * 4. In a dev build only, the server's raw words, because they are
 *    specific and the person reading them is debugging.
 * 5. The status's sentence.
 * 6. The caller's fallback, then the generic sentence. A plain ``Error``
 *    with a ``message`` ends here too: its message is English by
 *    construction ("Network Error", "timeout of 10000ms exceeded").
 *
 * Every call site improves without being touched, which is the point —
 * there are forty of them and migrating each by hand is forty chances to
 * miss one.
 */
export function getErrorDetail(err: unknown, fallback = ""): string {
  const code = getErrorCode(err)
  if (code) {
    // Dots separate keys in i18next and a code is full of them, so the
    // code is spelled with underscores in the catalogue. Asked with
    // ``exists`` first: a missing key is a thrown error in tests and a
    // console line in production, and a code we have not written a
    // sentence for yet is neither of those — it is the ordinary case
    // this falls through on.
    const key = `errors.byCode.${code.replace(/\./g, "_")}`
    const context = getErrorContext(err) ?? {}
    // ``count`` drives the plural form — and a key that exists only in its
    // plural spellings (``_one``, ``_few``…) is found by ``exists`` only
    // when asked with a count. The backend names the number by what it
    // counts, so the sentence can use either spelling.
    const count = typeof context.attempt_count === "number" ? context.attempt_count : undefined
    const options = count === undefined ? context : { ...context, count }
    if (i18n.exists(key, options)) return i18n.t(key, options)
  }
  if (isAxiosError(err)) {
    if (!err.response) return i18n.t("errors.network")
    const status = err.response.status
    const detail: unknown = err.response.data?.detail
    if (status === 422 && isValidationList(detail)) return describeValidationErrors(detail)
    const raw = rawServerText(detail)
    if (raw) return raw
    if (status && STATUS_WITH_A_SENTENCE.has(status)) return i18n.t(`errors.byStatus.${status}`)
    if (status && status >= 500) return i18n.t("errors.byStatus.500")
  }
  return fallback || i18n.t("errors.generic")
}
