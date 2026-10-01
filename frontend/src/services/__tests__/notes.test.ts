/** Coming straight back to a lesson reads its note after the save from leaving it. */
import { afterEach, describe, expect, it, vi } from "vitest"

import api from "../api"
import { notesService } from "../notes"

describe("notesService", () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it("does not read a lesson's note while a save of it is in flight", async () => {
    const order: string[] = []
    let release: () => void = () => {}
    vi.spyOn(api, "put").mockImplementation(
      () =>
        new Promise((resolve) => {
          release = () => {
            order.push("put done")
            resolve({ data: { chapter_id: "c1", body: "AB", updated_at: null } })
          }
        }),
    )
    vi.spyOn(api, "get").mockImplementation(async () => {
      order.push("get")
      return { data: { chapter_id: "c1", body: "AB", updated_at: null } }
    })
    const saving = notesService.save("c1", "AB")
    const reading = notesService.get("c1")
    await new Promise((r) => setTimeout(r, 0))
    expect(order).toEqual([])
    release()
    await saving
    expect((await reading).body).toBe("AB")
    expect(order).toEqual(["put done", "get"])
  })
})
