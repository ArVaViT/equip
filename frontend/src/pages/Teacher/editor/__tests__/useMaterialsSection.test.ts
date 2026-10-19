/** A file that reached the bucket is not «upload failed» because the list could not be re-read. */
import { act, renderHook } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

const toast = vi.fn()
vi.mock("@/lib/toast", () => ({ toast: (o: unknown) => toast(o) }))
vi.mock("@/lib/supabase", () => ({ supabase: { storage: { from: () => ({}) } } }))

import i18n from "@/i18n/config"
import { storageService } from "@/services/storage"
import { useMaterialsSection } from "../useMaterialsSection"

describe("useMaterialsSection", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("en")
    vi.restoreAllMocks()
    toast.mockClear()
  })

  it("does not call a landed upload failed when only the list could not be re-read", async () => {
    vi.spyOn(storageService, "listCourseMaterials")
      .mockResolvedValueOnce([])
      .mockRejectedValueOnce(new Error("offline"))
    const upload = vi.spyOn(storageService, "uploadCourseMaterial").mockResolvedValue(undefined)
    const { result } = renderHook(() => useMaterialsSection("c1", vi.fn(async () => true)))
    const file = new File(["x"], "notes.pdf", { type: "application/pdf" })
    await act(async () => {
      await result.current.handleUpload({ target: { files: [file] } } as never)
    })
    expect(upload).toHaveBeenCalledTimes(1)
    expect(toast).toHaveBeenCalledTimes(1)
    // The reason the list is missing — not «Upload failed», which had the
    // teacher uploading the same file again.
    expect(toast.mock.calls[0]?.[0]).not.toMatchObject({ title: "Upload failed" })
  })
})
