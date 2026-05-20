import { afterEach, describe, expect, it, vi } from "vitest"
import { waitForSelector } from "../grandTour"

afterEach(() => {
  document.body.innerHTML = ""
})

describe("waitForSelector", () => {
  it("resolves synchronously when the element already exists", async () => {
    const el = document.createElement("div")
    el.setAttribute("data-tour", "preexisting")
    document.body.appendChild(el)

    const result = await waitForSelector('[data-tour="preexisting"]', 1000)
    expect(result).toBe(el)
  })

  it("resolves when the element is appended after the call", async () => {
    const pending = waitForSelector('[data-tour="appears-later"]', 2000)
    // Append on the next tick so the MutationObserver actually fires
    setTimeout(() => {
      const el = document.createElement("section")
      el.setAttribute("data-tour", "appears-later")
      document.body.appendChild(el)
    }, 30)

    const result = await pending
    expect(result).not.toBeNull()
    expect((result as Element).getAttribute("data-tour")).toBe("appears-later")
  })

  it("resolves null on timeout when the element never appears", async () => {
    vi.useFakeTimers()
    const pending = waitForSelector('[data-tour="never"]', 500)
    await vi.advanceTimersByTimeAsync(600)
    const result = await pending
    expect(result).toBeNull()
    vi.useRealTimers()
  })

  it("only resolves once even when the element is added multiple times", async () => {
    const pending = waitForSelector('[data-tour="dup"]', 2000)
    setTimeout(() => {
      const a = document.createElement("div")
      a.setAttribute("data-tour", "dup")
      document.body.appendChild(a)
      // Second match shortly after — observer should already have
      // been disconnected, no double resolve, no errors.
      const b = document.createElement("div")
      b.setAttribute("data-tour", "dup")
      document.body.appendChild(b)
    }, 20)
    const result = await pending
    expect(result).not.toBeNull()
  })
})
