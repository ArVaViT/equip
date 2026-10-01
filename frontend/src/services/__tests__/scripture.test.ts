/** A lesson's blocks ask for their verses together, in one request. */
import { afterEach, describe, expect, it, vi } from "vitest"

import api from "../api"
import { scriptureService } from "../scripture"

describe("scriptureService.passagesIn", () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it("sends the blocks of one render as one request, and skips text with no verse numbers", async () => {
    const post = vi.spyOn(api, "post").mockResolvedValue({
      data: [[{ written: "Ин 3:16", ref: "john 3:16", text: "t1", edition: "nrt" }], []],
    })
    const [a, b, c] = await Promise.all([
      scriptureService.passagesIn("Ин 3:16 batch"),
      scriptureService.passagesIn("Рим 8:28 batch"),
      scriptureService.passagesIn("Нет ссылок"),
    ])
    expect(post).toHaveBeenCalledTimes(1)
    expect(post).toHaveBeenCalledWith("/scripture/passages", { texts: ["Ин 3:16 batch", "Рим 8:28 batch"] })
    expect(a.map((p) => p.ref)).toEqual(["john 3:16"])
    expect(b).toEqual([])
    expect(c).toEqual([])
  })

  it("does not remember a failure", async () => {
    const post = vi.spyOn(api, "post").mockRejectedValueOnce(new Error("offline"))
    expect(await scriptureService.passagesIn("Деян 1:8 fail")).toEqual([])
    post.mockResolvedValueOnce({ data: [[]] })
    await scriptureService.passagesIn("Деян 1:8 fail")
    expect(post).toHaveBeenCalledTimes(2)
  })

  it("splits a long lesson into requests the server accepts", async () => {
    const post = vi.spyOn(api, "post").mockImplementation(async (_url, body) => ({
      data: (body as { texts: string[] }).texts.map(() => []),
    }))
    const block = (i: number) => `Ин 3:16 long ${i} ${"x".repeat(20_000)}`
    await Promise.all([0, 1, 2, 3].map((i) => scriptureService.passagesIn(block(i))))
    const sizes = post.mock.calls.map(([, body]) => (body as { texts: string[] }).texts.join("").length)
    expect(post.mock.calls.length).toBeGreaterThan(1)
    expect(Math.max(...sizes)).toBeLessThanOrEqual(50_000)
  })
})
