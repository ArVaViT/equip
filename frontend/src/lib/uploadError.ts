/**
 * What to tell a person when a file upload cannot happen — before it is
 * sent, and after Storage has refused it.
 *
 * Supabase Storage answers in English written for a developer:
 * "The object exceeded the maximum allowed size", "mime type image/heic is
 * not supported", "Invalid key: …". Those sentences went straight into the
 * toast, on a screen that was otherwise entirely Russian, and one call
 * site swallowed the error altogether and said only "Загрузка не удалась".
 * The teacher had no way to tell a 60 MB recording from a lost connection.
 *
 * Two entry points:
 *
 * - `preflightUpload` looks at the file the same way the bucket will and
 *   returns the sentence to show if the bucket would refuse it. Cheap, and
 *   it spares a 40 MB upload that was always going to end in a 413.
 * - `describeUploadError` translates what Storage (or the API call that
 *   follows the upload) actually said. Nothing English reaches the toast.
 */

import { isAxiosError } from "axios"

import i18n from "@/i18n/config"
import { formatNumber } from "@/i18n/number"
import { getErrorDetail } from "@/lib/errorDetail"
import {
  type BucketSpec,
  formatList,
  isHeic,
  maxMb,
  MB,
  resolveContentType,
} from "@/lib/uploadLimits"

export type PreflightKind = "heic" | "type" | "size"

export interface PreflightIssue {
  /** So a caller with two toast titles can pick the right one. */
  kind: PreflightKind
  /** A complete sentence in the reader's language. */
  message: string
}

/** The file's size and the bucket's cap, the way the bucket sees them. */
export function preflightUpload(file: File, spec: BucketSpec): PreflightIssue | null {
  if (isHeic(file)) {
    return { kind: "heic", message: i18n.t("errors.storage.heic") }
  }
  if (resolveContentType(file, spec) === null) {
    return {
      kind: "type",
      message: i18n.t("errors.storage.unsupportedType", { formats: formatList(spec) }),
    }
  }
  if (file.size > spec.maxBytes) {
    return {
      kind: "size",
      message: i18n.t("errors.storage.tooLarge", {
        sizeMb: formatNumber(file.size / MB, 1),
        maxMb: maxMb(spec),
      }),
    }
  }
  return null
}

/** The fields a `StorageApiError` / `StorageUnknownError` carry, read
 *  without importing the classes: duck-typing survives a supabase-js bump
 *  that moves them, and a test can hand in a plain object. */
interface StorageErrorShape {
  status?: unknown
  statusCode?: unknown
  code?: unknown
  message?: unknown
  originalError?: unknown
}

function isNetworkFailure(err: unknown, shape: StorageErrorShape): boolean {
  // `fetch` rejects with a TypeError when the request never got an
  // answer ("Failed to fetch", "Load failed", "NetworkError when
  // attempting to fetch resource"); storage-js wraps that as a
  // StorageUnknownError with the TypeError under `originalError`.
  if (err instanceof TypeError) return true
  if (shape.originalError instanceof TypeError) return true
  if ("originalError" in shape && shape.originalError !== undefined) return true
  return typeof navigator !== "undefined" && navigator.onLine === false
}

/**
 * A sentence for the toast describing why an upload failed.
 *
 * The upload is usually followed by an API call that records the file
 * on the block or the course, and the two share a `catch`; an Axios
 * error is handed to `getErrorDetail`, which already speaks the reader's
 * language. Everything else is treated as Storage's answer.
 */
export function describeUploadError(err: unknown, spec: BucketSpec): string {
  if (isAxiosError(err)) return getErrorDetail(err)

  const shape: StorageErrorShape = typeof err === "object" && err !== null ? err : {}
  const message = typeof shape.message === "string" ? shape.message : ""
  const code = typeof shape.code === "string" ? shape.code : ""
  const status =
    typeof shape.status === "number"
      ? shape.status
      : Number.parseInt(typeof shape.statusCode === "string" ? shape.statusCode : "", 10)

  if (
    status === 413 ||
    /EntityTooLarge|Payload too large/i.test(code) ||
    /exceeded the maximum allowed size/i.test(message)
  ) {
    return i18n.t("errors.storage.tooLargeServer", { maxMb: maxMb(spec) })
  }
  if (status === 415 || /InvalidMimeType|invalid_mime_type/i.test(code) || /mime type/i.test(message)) {
    return i18n.t("errors.storage.unsupportedType", { formats: formatList(spec) })
  }
  if (/InvalidKey/i.test(code) || /^Invalid key/i.test(message)) {
    return i18n.t("errors.storage.invalidName")
  }
  if (status === 401 || status === 403 || /AccessDenied|Unauthorized|InvalidJWT/i.test(code)) {
    return i18n.t("errors.storage.forbidden")
  }
  if (isNetworkFailure(err, shape)) {
    return i18n.t("errors.storage.network")
  }
  // A code is an identifier, not English prose, and it is what support
  // will ask for; the sentence around it is translated.
  if (code && /^[A-Za-z_]+$/.test(code)) {
    return i18n.t("errors.storage.genericWithCode", { code })
  }
  return i18n.t("errors.storage.generic")
}
