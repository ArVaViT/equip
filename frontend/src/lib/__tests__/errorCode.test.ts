/**
 * Pin the contract between `getErrorCode` / `getErrorContext` and the
 * backend's typed error envelope (Phase 5ay). These tests are the
 * canonical examples of how a route handler should react to a typed
 * code; the existing string-detail fallback path is also pinned so
 * routes that haven't migrated yet keep working.
 */

import { describe, expect, it } from "vitest"

import { getErrorCode } from "../errorCode"

function fakeAxiosError(body: unknown, status = 400): unknown {
  // Shape mirrors what `axios.isAxiosError` accepts. The
  // `isAxiosError` flag is the marker the runtime check uses.
  return {
    isAxiosError: true,
    response: { status, data: body },
  }
}

describe("getErrorCode", () => {
  it("returns the code when the backend used equip_error", () => {
    const err = fakeAxiosError({
      detail: {
        code: "course.already_enrolled",
        message: "You're already enrolled in this course",
        context: { course_id: "abc" },
      },
    })
    expect(getErrorCode(err)).toBe("course.already_enrolled")
  })

  it("returns null for the legacy string-detail shape", () => {
    const err = fakeAxiosError({ detail: "Course 'abc' not found" })
    expect(getErrorCode(err)).toBeNull()
  })

  it("returns null when the response has no body", () => {
    const err = fakeAxiosError(undefined)
    expect(getErrorCode(err)).toBeNull()
  })

  it("returns null when the error is not an axios error at all", () => {
    expect(getErrorCode(new Error("boom"))).toBeNull()
    expect(getErrorCode("plain string")).toBeNull()
    expect(getErrorCode(null)).toBeNull()
  })
})
