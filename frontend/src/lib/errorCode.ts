/**
 * Typed error-code envelope on top of `getErrorDetail`.
 *
 * The backend started emitting structured errors in Phase 5ay:
 *
 *   { detail: { code: "course.not_published", message: "...", context: {...} } }
 *
 * instead of the legacy `{ detail: "..." }` (a plain string). This
 * module gives the frontend a typed switch:
 *
 *   const code = getErrorCode(err)
 *   switch (code) {
 *     case "course.already_enrolled": ...
 *   }
 *
 * Routes that haven't migrated yet still return the string-detail
 * shape; `getErrorCode` returns `null` for those so the caller falls
 * back to `getErrorDetail` for the toast text. No flag day required.
 */

import { isAxiosError } from "axios"

/**
 * Stable machine-readable identifiers mirror
 * `backend/app/core/errors.py::ErrorCode`. Sorted by feature scope.
 *
 * To add a code:
 *   1. Append the value to `ErrorCode` in the backend.
 *   2. Append the same string to this union.
 *   3. The exhaustiveness check on `switch (code)` calls catches
 *      every consumer that needs to handle it.
 */
export type ErrorCode =
  // auth / permissions
  | "auth.required"
  | "auth.forbidden"
  | "account.deactivated"
  // generic resource lookups
  | "resource.not_found"
  // course lifecycle
  | "course.not_published"
  | "course.already_enrolled"
  | "course.enrolment_closed"
  // translation pipeline
  | "translation.disabled"
  | "translation.worker_unauthorized"
  | "translation.worker_unconfigured"
  // quiz / assignment
  | "quiz.not_open"
  | "quiz.attempts_exhausted"
  // daily challenge
  | "daily_challenge.not_scheduled"
  | "daily_challenge.not_translated"
  | "daily_challenge.already_attempted"
  | "daily_challenge.invalid_option"
  | "daily_challenge.archive_date_not_allowed"
  // invitations
  | "invitation.not_found"
  | "invitation.expired"
  | "invitation.already_used"
  | "invitation.email_mismatch"
  // validation
  | "validation.failed"

interface StructuredErrorDetail {
  code: ErrorCode
  message: string
  context?: Record<string, unknown>
}

function isStructuredErrorDetail(value: unknown): value is StructuredErrorDetail {
  return (
    typeof value === "object" &&
    value !== null &&
    "code" in value &&
    typeof (value as { code: unknown }).code === "string" &&
    "message" in value &&
    typeof (value as { message: unknown }).message === "string"
  )
}

/**
 * Return the structured error code from an Axios error response, or
 * `null` when the backend returned a legacy string detail (or the
 * error isn't an Axios error at all). Never throws.
 */
export function getErrorCode(err: unknown): ErrorCode | null {
  if (!isAxiosError(err)) return null
  const detail: unknown = err.response?.data?.detail
  return isStructuredErrorDetail(detail) ? detail.code : null
}
