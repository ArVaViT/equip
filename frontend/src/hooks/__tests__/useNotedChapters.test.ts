/** The lessons a reader has a note on, for marking them in a list. */
import { createElement, type ReactNode } from "react"
import { renderHook, waitFor } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"

import { AuthContext } from "@/context/auth-context"
import { notesService } from "@/services/notes"


import { useNotedChapters } from "../useNotedChapters"

const wrapper = ({ children }: { children: ReactNode }) =>
  createElement(AuthContext.Provider, { value: { user: { id: "u1" } } as never }, children)

describe("useNotedChapters", () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it("is the set of lessons with a note", async () => {
    vi.spyOn(notesService, "notedChapters").mockResolvedValue(["c1", "c3"])
    const { result } = renderHook(() => useNotedChapters(), { wrapper })
    await waitFor(() => expect([...result.current]).toEqual(["c1", "c3"]))
  })

  it("is empty when the notes cannot be read", async () => {
    const mine = vi.spyOn(notesService, "notedChapters").mockRejectedValue(new Error("offline"))
    const { result } = renderHook(() => useNotedChapters(), { wrapper })
    await waitFor(() => expect(mine).toHaveBeenCalled())
    expect(result.current.size).toBe(0)
  })
})
