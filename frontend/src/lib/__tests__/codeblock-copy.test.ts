import { describe, expect, it, vi, beforeEach, afterEach } from "vitest"
import { attachCopyButtonsIn } from "../codeblock-copy"

const LABELS = {
  copy: "Copy",
  copied: "Copied",
  ariaLabel: "Copy code to clipboard",
}

function makeContainer(innerHTML: string): HTMLDivElement {
  const div = document.createElement("div")
  div.innerHTML = innerHTML
  return div
}

describe("attachCopyButtonsIn", () => {
  beforeEach(() => {
    Object.defineProperty(navigator, "clipboard", {
      value: { writeText: vi.fn().mockResolvedValue(undefined) },
      writable: true,
      configurable: true,
    })
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  it("attaches a Copy button to every <pre> block", () => {
    const container = makeContainer(
      "<pre><code>const a = 1</code></pre>" +
        "<p>plain text between blocks</p>" +
        "<pre><code>print(2)</code></pre>",
    )
    attachCopyButtonsIn(container, LABELS)
    const buttons = container.querySelectorAll("pre > button")
    expect(buttons.length).toBe(2)
    expect(buttons[0]?.textContent).toBe("Copy")
    expect(buttons[0]?.getAttribute("aria-label")).toBe(
      "Copy code to clipboard",
    )
  })

  it("is idempotent — second pass does not duplicate buttons", () => {
    const container = makeContainer(
      "<pre><code>const a = 1</code></pre>",
    )
    attachCopyButtonsIn(container, LABELS)
    attachCopyButtonsIn(container, LABELS)
    expect(container.querySelectorAll("pre > button").length).toBe(1)
  })

  it("writes the inner code text to clipboard on click", async () => {
    const container = makeContainer(
      "<pre><code>const x = 42</code></pre>",
    )
    attachCopyButtonsIn(container, LABELS)
    const button = container.querySelector("pre > button") as HTMLButtonElement
    button.click()
    // Microtask + async clipboard call; flush.
    await vi.runAllTimersAsync()
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith("const x = 42")
  })

  it("flashes the Copied label after a successful copy", async () => {
    const container = makeContainer("<pre><code>x</code></pre>")
    attachCopyButtonsIn(container, LABELS)
    const button = container.querySelector("pre > button") as HTMLButtonElement
    button.click()
    // Allow the awaited clipboard promise to resolve so the
    // post-resolve mutation runs.
    await Promise.resolve()
    expect(button.textContent).toBe("Copied")
    vi.advanceTimersByTime(1500)
    expect(button.textContent).toBe("Copy")
  })

  it("falls back silently if clipboard.writeText rejects", async () => {
    Object.defineProperty(navigator, "clipboard", {
      value: { writeText: vi.fn().mockRejectedValue(new Error("denied")) },
      writable: true,
      configurable: true,
    })
    const container = makeContainer("<pre><code>x</code></pre>")
    attachCopyButtonsIn(container, LABELS)
    const button = container.querySelector("pre > button") as HTMLButtonElement
    // Should not throw despite the rejection.
    expect(() => button.click()).not.toThrow()
  })

  it("does nothing when container is null", () => {
    expect(() => attachCopyButtonsIn(null, LABELS)).not.toThrow()
  })
})
