import { describe, expect, it } from "vitest"
import { gradePair } from "../gradePair"

describe("gradePair", () => {
  it("formats both sides through the one formatter", () => {
    // Same text on every screen is the whole of D14 reduced to a string.
    expect(gradePair(100, 25, "A", "F")).toEqual({
      current: "100.0% A",
      final: "25.0% F",
      differ: true,
    })
  })

  it("reports no difference when the two are equal", () => {
    // The caller then prints one number and drops the explanation — there is
    // nothing to explain.
    expect(gradePair(80, 80, "B", "B").differ).toBe(false)
  })

  it("compares the numbers, not the text they round to", () => {
    // 74.04 and 74.03 both print "74.0%". Saying "final 74.0%" underneath
    // "74.0%" would be a line of explanation for a difference nobody can see.
    expect(gradePair(74.04, 74.03, "C", "C").differ).toBe(true)
    expect(gradePair(74.04, 74.04, "C", "C").differ).toBe(false)
  })

  it("drops the symbol on a scheme that has none", () => {
    expect(gradePair(91, 91, null, null).current).toBe("91.0%")
  })

  it("keeps a symbol on one side even when the other lacks it", () => {
    // Crossing a band boundary is exactly when the pair matters most.
    const pair = gradePair(90, 55, "A", "F")

    expect(pair.current).toBe("90.0% A")
    expect(pair.final).toBe("55.0% F")
  })
})
