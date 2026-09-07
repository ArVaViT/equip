import { describe, expect, it, vi } from "vitest"

/**
 * driver.js's × button, in the reader's language.
 *
 * Everything else in the tour popover is translated — next, previous, done,
 * the progress line — because driver.js takes those as options. The close
 * button is not among them: the library hard-codes `aria-label="Close"`, so
 * a Russian reader's screen reader announced an English word on an otherwise
 * Russian page. Found by reading the dialog's accessibility properties while
 * walking the first-run flow.
 *
 * The fix rides on `onPopoverRender`, which is easy to drop in a refactor and
 * impossible to notice by looking: the button still works, it just says the
 * wrong thing to the people who cannot see it.
 */

const captured: { config?: Record<string, unknown> } = {}

vi.mock("driver.js", () => ({
  driver: (config: Record<string, unknown>) => {
    captured.config = config
    return { destroy: vi.fn(), drive: vi.fn(), moveNext: vi.fn(), movePrevious: vi.fn() }
  },
}))
vi.mock("dompurify", () => ({
  default: { sanitize: (html: string) => html, addHook: vi.fn(), removeHook: vi.fn() },
}))

const { createEditorialTour } = await import("../tour")

describe("the tour's close button", () => {
  it("is named in the reader's language", async () => {
    await createEditorialTour({
      steps: [{ element: "body", popover: { title: "Шаг", description: "Описание" } }],
      labels: { next: "Дальше", previous: "Назад", done: "Готово", progress: "{{current}}/{{total}}", close: "Закрыть" },
    })

    const onPopoverRender = captured.config?.onPopoverRender as
      | ((popover: { closeButton?: HTMLElement }) => void)
      | undefined
    expect(onPopoverRender, "no onPopoverRender — the × keeps driver.js's English name").toBeTypeOf("function")

    const closeButton = document.createElement("button")
    closeButton.setAttribute("aria-label", "Close")
    onPopoverRender!({ closeButton })

    expect(closeButton.getAttribute("aria-label")).toBe("Закрыть")
  })
})
