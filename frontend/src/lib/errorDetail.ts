import { isAxiosError } from "axios"

import i18n from "@/i18n/config"
import { getErrorCode } from "@/lib/errorCode"

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
 * The message to show a person, in their own language where we have one.
 *
 * The server's ``message`` is English prose — it is written for a log and
 * for a developer reading a response — and it used to be returned straight
 * into a toast. A German student who ran out of quiz attempts was told so
 * in English, on a page that was otherwise entirely German.
 *
 * The structured envelope already carries a ``code``, and a code is
 * translatable in a way free prose is not. So: the code's own sentence
 * first, the server's message second (it is at least specific), the
 * status's sentence third, and the caller's fallback last. Every call
 * site improves without being touched, which is the point — there are
 * thirty-three of them and migrating each by hand is thirty-three
 * chances to miss one.
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
    if (i18n.exists(key)) return i18n.t(key)
  }
  if (isAxiosError(err)) {
    const detail: unknown = err.response?.data?.detail
    if (typeof detail === "string") return detail
    // Phase 5ay: structured envelope ``{code, message, context}``.
    // Render ``message`` for the toast; ``getErrorCode`` extracts
    // the typed code for switch logic separately.
    if (
      detail &&
      typeof detail === "object" &&
      "message" in detail &&
      typeof (detail as { message: unknown }).message === "string"
    ) {
      return (detail as { message: string }).message
    }
    if (detail) {
      const pretty = safeStringify(detail)
      if (pretty) return pretty
    }
    const status = err.response?.status
    if (status === 401) return i18n.t("errors.byStatus.401")
    if (status === 403) return i18n.t("errors.byStatus.403")
    if (status === 404) return i18n.t("errors.byStatus.404")
    if (status === 409) return i18n.t("errors.byStatus.409")
    if (status === 429) return i18n.t("errors.byStatus.429")
    if (status && status >= 500) return i18n.t("errors.byStatus.500")
  }
  if (err instanceof Error) return err.message
  return fallback || i18n.t("errors.generic")
}