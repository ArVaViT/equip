import { describe, expect, it } from "vitest"

import { describeBands } from "../bandRanges"

const plain = (n: number) => String(n)

describe("describeBands", () => {
  it("turns floors into ranges, the top band running to 100", () => {
    expect(
      describeBands(
        [
          [90, "A"],
          [80, "B"],
          [70, "C"],
          [60, "D"],
          [0, "F"],
        ],
        plain,
      ),
    ).toBe("A 90–100 · B 80–89 · C 70–79 · D 60–69 · F 0–59")
  })

  it("reads the five-point table the same way", () => {
    expect(
      describeBands(
        [
          [90, "5"],
          [75, "4"],
          [70, "3"],
          [0, "2"],
        ],
        plain,
      ),
    ).toBe("5 90–100 · 4 75–89 · 3 70–74 · 2 0–69")
  })

  it("names a one-point band by its single value instead of «70–70»", () => {
    expect(describeBands([[71, "A"], [70, "B"], [0, "F"]], plain)).toBe("A 71–100 · B 70 · F 0–69")
  })

  it("falls back to floors when a line is drawn between whole numbers", () => {
    // «B 80–89» would leave 89.7 in no band; «≥» is honest about the boundary.
    expect(describeBands([[89.5, "A"], [80, "B"], [0, "F"]], plain)).toBe("A ≥ 89.5 · B ≥ 80 · F ≥ 0")
  })

  it("has nothing to say for a scheme without bands", () => {
    expect(describeBands([], plain)).toBe("")
  })
})
