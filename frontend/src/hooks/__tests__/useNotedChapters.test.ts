/** The lessons a reader has a note on, for marking them in a list. */
import { renderHook, waitFor } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"

import { notesService } from "@/services/notes"

vi.mock("@/context/useAuth", () => ({ useAuth: () => ({ user: { id: "u1" } }) }))

import { useNotedChapters } from "../useNotedChapters"

describe("useNotedChapters", () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it("is the set of lessons with a note", async () => {
    vi.spyOn(notesService, "notedChapters").mockResolvedValue(["c1", "c3"])
    const { result } = renderHook(() => useNotedChapters())
    await waitFor(() => expect([...result.current]).toEqual(["c1", "c3"]))
  })

  it("is empty when the notes cannot be read", async () => {
    const mine = vi.spyOn(notesService, "notedChapters").mockRejectedValue(new Error("offline"))
    const { result } = renderHook(() => useNotedChapters())
    await waitFor(() => expect(mine).toHaveBeenCalled())
    expect(result.current.size).toBe(0)
  })
})
