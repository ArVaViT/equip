import { describe, expect, it, vi } from "vitest"

const success = vi.fn()
vi.mock("sonner", () => ({
  toast: Object.assign(vi.fn(), { success, error: vi.fn(), warning: vi.fn(), info: vi.fn() }),
}))

describe("toast — an action on the toast", () => {
  it("carries the Undo button and a longer life to sonner", async () => {
    const { toast } = await import("../toast")
    const onClick = vi.fn()
    toast({ title: "Урок удалён", variant: "success", duration: 8000, action: { label: "Отменить", onClick } })
    expect(success).toHaveBeenCalledWith("Урок удалён", { action: { label: "Отменить", onClick }, duration: 8000 })
  })

  it("passes nothing extra when there is nothing to act on", async () => {
    const { toast } = await import("../toast")
    toast({ title: "Сохранено", variant: "success" })
    expect(success).toHaveBeenLastCalledWith("Сохранено", undefined)
  })
})
