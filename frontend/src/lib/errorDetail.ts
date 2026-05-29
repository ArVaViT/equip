import { isAxiosError } from "axios"

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

export function getErrorDetail(err: unknown, fallback = "An error occurred"): string {
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
    if (status === 401) return "Authentication required. Please sign in again."
    if (status === 403) return "You don't have permission for this action."
    if (status === 404) return "Resource not found."
    if (status === 409) return "This conflicts with current data. Please refresh and retry."
    if (status === 429) return "Too many requests. Please slow down and try again."
    if (status && status >= 500) return "Server error. Please try again later."
  }
  if (err instanceof Error) return err.message
  return fallback
}