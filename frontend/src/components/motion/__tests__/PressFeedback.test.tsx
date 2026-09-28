import { createRef } from "react"
import { fireEvent, render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import { PressFeedback } from "../PressFeedback"

const reducedMotion = vi.hoisted(() => ({ value: false }))
vi.mock("motion/react", async (importOriginal) => ({
  ...(await importOriginal<typeof import("motion/react")>()),
  useReducedMotion: () => reducedMotion.value,
}))

/**
 * `PressFeedback` sits inside `TooltipTrigger asChild` in the header. Radix's
 * `Slot` gives its child the ref the tooltip anchors to and the pointer
 * handlers that open it; the component used to drop both, and the menu
 * tooltips never opened. Both motion modes render a different element, so
 * both are checked.
 */
describe("PressFeedback", () => {
  for (const reduce of [false, true]) {
    it(`hands the ref and the props a trigger passes to its element (reduced motion: ${reduce})`, () => {
      reducedMotion.value = reduce
      const ref = createRef<HTMLDivElement>()
      const onPointerEnter = vi.fn()

      render(
        <PressFeedback ref={ref} data-state="closed" onPointerEnter={onPointerEnter}>
          <span>inside</span>
        </PressFeedback>,
      )

      const element = screen.getByText("inside").parentElement
      expect(ref.current).toBe(element)
      expect(element?.getAttribute("data-state")).toBe("closed")
      fireEvent.pointerEnter(element!)
      expect(onPointerEnter).toHaveBeenCalled()
    })
  }
})
