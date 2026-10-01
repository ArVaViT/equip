import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { OptionButton } from "../OptionButton"

/**
 * A long answer is shown whole. The row cut it off with an ellipsis, so on
 * a phone a reader chose between answers they could not finish reading.
 */
describe("OptionButton", () => {
  it("shows a long answer in full, wrapping instead of cutting it off", () => {
    const text =
      "Мария Магдалина, Мария, мать Иакова, и Саломия, которые пришли ко гробу рано утром в первый день недели"
    render(
      <OptionButton
        option={{ id: "o1", option_text: text, order_index: 0 } as never}
        reveal={null}
        disabled={false}
        onClick={() => {}}
      />,
    )
    const span = screen.getByText(text)
    expect(span.className).not.toContain("truncate")
    expect(span.className).toContain("break-words")
  })
})
