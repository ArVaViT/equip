import { afterEach, describe, expect, it, vi } from "vitest"

afterEach(() => {
  delete (document as unknown as { modelContext?: unknown }).modelContext
  delete (navigator as unknown as { modelContext?: unknown }).modelContext
  vi.unstubAllGlobals()
  vi.resetModules()
})

async function load() {
  return import("../webmcp")
}

describe("WebMCP tools", () => {
  it("registers on document.modelContext, the current API", async () => {
    const registerTool = vi.fn()
    Object.assign(document, { modelContext: { registerTool } })
    const { registerWebMcpTools } = await load()
    registerWebMcpTools()
    registerWebMcpTools()
    expect(registerTool.mock.calls.map(([tool]) => tool.name)).toEqual(["search_courses", "get_course"])
    for (const [tool] of registerTool.mock.calls) expect(tool.annotations.readOnlyHint).toBe(true)
  })

  it("falls back to navigator.modelContext, the early preview", async () => {
    const registerTool = vi.fn().mockRejectedValue(new Error("nope"))
    Object.assign(navigator, { modelContext: { registerTool } })
    const { registerWebMcpTools } = await load()
    expect(() => registerWebMcpTools()).not.toThrow()
    expect(registerTool).toHaveBeenCalledTimes(2)
  })

  it("does nothing where WebMCP is missing", async () => {
    const { findModelContext, registerWebMcpTools } = await load()
    expect(findModelContext()).toBeNull()
    expect(() => registerWebMcpTools()).not.toThrow()
  })

  it("searches the public catalogue without the reader's credentials", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => [{ id: "b8d24482-f630-49dc-990a-72ddb0717de0", title: "Acts", description: "A course", chapter_count: 13 }],
    })
    vi.stubGlobal("fetch", fetchMock)
    const { searchCourses } = await load()
    const result = await searchCourses({ query: "acts", limit: 500 })
    const [url, init] = fetchMock.mock.calls[0]!
    expect(url).toContain("/api/v1/courses?limit=50&search=acts")
    expect(init.credentials).toBe("omit")
    expect(init.headers.Authorization).toBeUndefined()
    const body = JSON.parse(result.content[0]!.text)
    expect(body.courses[0].url).toBe("https://equipbible.com/courses/b8d24482-f630-49dc-990a-72ddb0717de0")
  })

  it("refuses a course id that is not one", async () => {
    const fetchMock = vi.fn()
    vi.stubGlobal("fetch", fetchMock)
    const { getCourse } = await load()
    const result = await getCourse({ id: "../users/me" })
    expect(result.isError).toBe(true)
    expect(fetchMock).not.toHaveBeenCalled()
  })
})
