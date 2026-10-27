import { fireEvent, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { ConnectionStatus } from "../ConnectionStatus"

const originalOnLine = Object.getOwnPropertyDescriptor(navigator, "onLine")

function setOnline(online: boolean) {
  Object.defineProperty(navigator, "onLine", { configurable: true, value: online })
}

afterEach(() => {
  if (originalOnLine) Object.defineProperty(navigator, "onLine", originalOnLine)
  vi.restoreAllMocks()
})

describe("ConnectionStatus", () => {
  it("announces both current connectivity states", () => {
    setOnline(true)
    const { rerender } = render(<ConnectionStatus />)
    expect(screen.getByRole("status").textContent).toContain("Online")

    setOnline(false)
    fireEvent(window, new Event("offline"))
    rerender(<ConnectionStatus />)
    expect(screen.getByRole("status").textContent).toContain("Offline")

    setOnline(true)
    fireEvent(window, new Event("online"))
    rerender(<ConnectionStatus />)
    expect(screen.getByRole("status").textContent).toContain("Online")
  })
})
