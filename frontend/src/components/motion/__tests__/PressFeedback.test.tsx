import { createRef } from "react"
import { fireEvent, render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import { PressFeedback } from "../PressFeedback"

/**
 * `PressFeedback` sits inside `TooltipTrigger asChild` in the header. Radix's
 * `Slot` gives its child the ref the tooltip anchors to and the pointer
 * handlers that open it; the component used to drop both, and the menu
 * tooltips never opened.
 */
describe("PressFeedback", () => {
  it("hands the ref and the props a trigger passes to its element", () => {
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

  it("presses in with CSS only, and only when motion is welcome", () => {
    // The header renders this on every page; a motion.div here pulled the
    // whole motion runtime into the first load (2026-09-30 audit, F1).
    render(
      <PressFeedback className="inline-flex">
        <span>inside</span>
      </PressFeedback>,
    )
    const element = screen.getByText("inside").parentElement!
    expect(element.className).toContain("motion-safe:active:scale-[0.97]")
    expect(element.className).toContain("inline-flex")
  })
})
