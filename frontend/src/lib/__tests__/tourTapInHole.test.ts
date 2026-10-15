import { beforeEach, describe, expect, it, vi } from "vitest"

/**
 * A tap on what the tour points at closes the tour.
 *
 * While a step is lit, the spotlit element is inert
 * (`disableActiveInteraction`) and the overlay has a hole over it, so the
 * tap lands on <body>. driver.js closes on a tap on the overlay and has no
 * answer for the hole. On 2026-10-15 a teacher on a phone met the
 * student-progress tour ("click a student…"), tapped the students six
 * times — every tap recorded on <body> — and only got out through the 24px
 * ×. This pins that a tap in the hole is treated as a tap on the overlay,
 * and that nothing else is.
 */

const destroy = vi.fn()
const captured: { config?: Record<string, unknown> } = {}

vi.mock("driver.js", () => ({
  driver: (config: Record<string, unknown>) => {
    captured.config = config
    return { destroy, drive: vi.fn(), moveNext: vi.fn(), movePrevious: vi.fn() }
  },
}))
vi.mock("dompurify", () => ({
  default: { sanitize: (html: string) => html, addHook: vi.fn(), removeHook: vi.fn() },
}))

const { createEditorialTour } = await import("../tour")

async function startTour() {
  await createEditorialTour({
    steps: [{ element: "body", popover: { title: "Шаг", description: "Описание" } }],
    labels: { next: "Дальше", previous: "Назад", done: "Готово", progress: "{{current}}/{{total}}", close: "Закрыть" },
  })
  const config = captured.config as {
    onPopoverRender: (popover: { closeButton?: HTMLElement }) => void
    onDestroyed: () => void
  }
  // driver.js calls this when a step's popover is on screen.
  config.onPopoverRender({})
  return config
}

describe("a tap on what the tour is pointing at", () => {
  beforeEach(() => {
    destroy.mockClear()
  })

  it("closes the tour", async () => {
    const config = await startTour()
    document.body.click()
    expect(destroy).toHaveBeenCalledTimes(1)
    config.onDestroyed()
  })

  it("does not close it from a tap on the tour's own controls", async () => {
    const config = await startTour()
    const next = document.createElement("button")
    document.body.appendChild(next)
    next.click()
    expect(destroy).not.toHaveBeenCalled()
    next.remove()
    config.onDestroyed()
  })

  it("stops listening once the tour is gone", async () => {
    const config = await startTour()
    config.onDestroyed()
    document.body.click()
    expect(destroy).not.toHaveBeenCalled()
  })
})
