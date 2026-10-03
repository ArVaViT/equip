/**
 * «Prepare translations» is fired and forgotten by the editor. A refusal used
 * to be an unhandled rejection and a spinner that simply stopped.
 */
import { act, renderHook, waitFor } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import { courseTranslationService } from "@/services/courseTranslation"
import { useCourseTranslation } from "../useCourseTranslation"

const toast = vi.fn()
vi.mock("@/lib/toast", () => ({ toast: (...args: unknown[]) => toast(...args) }))

describe("useCourseTranslation.prepare", () => {
  it("says so when the server refuses", async () => {
    vi.spyOn(courseTranslationService, "progress").mockRejectedValue(new Error("offline"))
    vi.spyOn(courseTranslationService, "prepare").mockRejectedValue(new Error("503"))
    const { result } = renderHook(() => useCourseTranslation("k1"))

    await act(() => result.current.prepare())

    await waitFor(() => expect(toast).toHaveBeenCalledWith(expect.objectContaining({ variant: "destructive" })))
    expect(result.current.preparing).toBe(false)
  })
})
