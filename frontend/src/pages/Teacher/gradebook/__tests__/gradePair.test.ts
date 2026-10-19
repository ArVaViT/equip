import { describe, expect, it } from "vitest"
import { gradePair } from "../gradePair"

describe("gradePair", () => {
  it("formats both sides through the one formatter", () => {
    // Same text on every screen is the whole of D14 reduced to a string.
    expect(gradePair(100, 25, "A", "F")).toEqual({
      current: "100.00% A",
      final: "25.00% F",
      differ: true,
    })
  })

  it("reports no difference when the two are equal", () => {
    // The caller then prints one number and drops the explanation — there is
    // nothing to explain.
    expect(gradePair(80, 80, "B", "B").differ).toBe(false)
  })

  it("compares the numbers, not the text they round to", () => {
    // 74.004 and 74.003 both print "74.00%". Saying "final 74.00%" underneath
    // "74.00%" would be a line of explanation for a difference nobody can see.
    expect(gradePair(74.004, 74.003, "C", "C").differ).toBe(true)
    expect(gradePair(74.004, 74.004, "C", "C").differ).toBe(false)
  })

  it("prints the grade at the precision its letter was chosen at", () => {
    // The backend rounds to two places and reads the band table from that
    // number. One place put 89.95 on the page as «90,0% B» beside a scale
    // that says 90 is an A (2026-10-19).
    expect(gradePair(89.95, 89.95, "B", "B").current).toBe("89.95% B")
  })

  it("drops the symbol on a scheme that has none", () => {
    expect(gradePair(91, 91, null, null).current).toBe("91.00%")
  })

  it("keeps a symbol on one side even when the other lacks it", () => {
    // Crossing a band boundary is exactly when the pair matters most.
    const pair = gradePair(90, 55, "A", "F")

    expect(pair.current).toBe("90.00% A")
    expect(pair.final).toBe("55.00% F")
  })
})
