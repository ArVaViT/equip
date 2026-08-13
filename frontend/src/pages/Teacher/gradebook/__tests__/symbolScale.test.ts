import { describe, expect, it } from "vitest"
import { symbolRank, symbolTone, type GradeBand } from "../symbolScale"

const LETTER: GradeBand[] = [
  [90, "A"],
  [80, "B"],
  [70, "C"],
  [60, "D"],
  [0, "F"],
]

const FIVE_POINT: GradeBand[] = [
  [90, "5"],
  [75, "4"],
  [70, "3"],
  [0, "2"],
]

describe("symbolRank", () => {
  it("ranks by position in the school's own scale", () => {
    expect(symbolRank("A", LETTER)).toBeGreaterThan(symbolRank("F", LETTER))
  })

  it("ranks a five-point scale, which the hardcoded table could not", () => {
    // The old `LETTER_ORDER` returned 0 for every one of these, so sorting a
    // five-point course by grade put «5» and «2» in the same bucket — and the
    // numbers in the next column stayed correct, so nothing looked wrong.
    expect(symbolRank("5", FIVE_POINT)).toBeGreaterThan(symbolRank("4", FIVE_POINT))
    expect(symbolRank("4", FIVE_POINT)).toBeGreaterThan(symbolRank("3", FIVE_POINT))
    expect(symbolRank("3", FIVE_POINT)).toBeGreaterThan(symbolRank("2", FIVE_POINT))
  })

  it("sorts an unknown symbol below every real one rather than equal to them", () => {
    // Equal-to-zero was the old behaviour and it silently merged the top of a
    // scale with the bottom of it.
    expect(symbolRank("щ", LETTER)).toBe(-1)
    expect(symbolRank("щ", LETTER)).toBeLessThan(symbolRank("F", LETTER))
  })

  it("follows a school that edits its scale rather than the shipped one", () => {
    const custom: GradeBand[] = [
      [95, "Отлично"],
      [80, "Хорошо"],
      [0, "Слабо"],
    ]

    expect(symbolRank("Отлично", custom)).toBeGreaterThan(symbolRank("Хорошо", custom))
  })
})

describe("symbolTone", () => {
  it("gives the top band the success tone and the bottom the failing one", () => {
    expect(symbolTone("A", LETTER)).toContain("success")
    expect(symbolTone("F", LETTER)).toContain("destructive")
  })

  it("treats the top of a five-point scale like the top of a letter one", () => {
    // Same position, same colour — without a second table to keep in step.
    expect(symbolTone("5", FIVE_POINT)).toBe(symbolTone("A", LETTER))
    expect(symbolTone("2", FIVE_POINT)).toBe(symbolTone("F", LETTER))
  })

  it("stays neutral for a symbol the scale does not contain", () => {
    expect(symbolTone("щ", LETTER)).toBe("bg-muted text-ink-muted")
  })

  it("survives an empty band list without dividing by zero", () => {
    expect(symbolTone("A", [])).toBe("bg-muted text-ink-muted")
  })

  it("handles a two-band scale, where every grade is either top or bottom", () => {
    const passFail: GradeBand[] = [
      [70, "Зачёт"],
      [0, "Незачёт"],
    ]

    expect(symbolTone("Зачёт", passFail)).toContain("success")
    expect(symbolTone("Незачёт", passFail)).toContain("destructive")
  })
})

describe("symbolTone across scale sizes", () => {
  const scaleOf = (n: number): GradeBand[] =>
    Array.from({ length: n }, (_, i) => [100 - i * 10, `s${i}`] as GradeBand)

  // The palette has five tones. A school defining more bands than that must
  // still never see a lower grade painted to look better than a higher one —
  // which is the property that actually matters, and the one that holds at any
  // size. Requiring every band to differ is impossible past five and was the
  // wrong thing to ask.
  const SEVERITY = [
    "bg-success/15 text-success-ink",
    "bg-info/15 text-info-ink",
    "bg-accent/20 text-ink",
    "bg-warning/15 text-warning-ink",
    "bg-destructive/15 text-destructive-ink",
  ]

  it.each([1, 2, 3, 4, 5, 6, 7, 12])("never paints a lower band better (%i bands)", (n) => {
    const bands = scaleOf(n)
    const ranks = bands.map(([, s]) => SEVERITY.indexOf(symbolTone(s, bands)))

    for (let i = 1; i < ranks.length; i++) {
      expect(ranks[i]!, `band ${i + 1} of ${n}`).toBeGreaterThanOrEqual(ranks[i - 1]!)
    }
  })

  it.each([2, 3, 4, 5])("keeps every band distinct while the palette allows (%i bands)", (n) => {
    const bands = scaleOf(n)
    const tones = bands.map(([, s]) => symbolTone(s, bands))

    expect(new Set(tones).size).toBe(n)
  })

  it("always paints the bottom band as failing, whatever the scale", () => {
    for (const n of [2, 3, 4, 5, 6]) {
      const bands = scaleOf(n)
      const last = bands[bands.length - 1]![1]

      expect(symbolTone(last, bands)).toContain("destructive")
    }
  })
})
