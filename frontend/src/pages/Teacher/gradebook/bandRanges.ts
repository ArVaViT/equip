import type { GradeBand } from "./symbolScale"

/**
 * The band table as one readable line: «A 90–100 · B 80–89 · … · F 0–59».
 *
 * The backend sends floors only (`[90, "A"], [80, "B"]`), which is the right
 * storage and the wrong display: a teacher reading «B 80» has to look at the
 * next row to learn where B ends. Each band's ceiling is the floor above it
 * minus one, and the top band runs to 100.
 *
 * «Minus one» is only true for whole-number floors. A school that draws a
 * line at 89.5 gets «B ≥ 80» instead — honest about the boundary rather than
 * a range that puts 89.7 in no band at all.
 */
export function describeBands(bands: GradeBand[], format: (n: number) => string): string {
  const wholeNumbers = bands.every(([floor]) => Number.isInteger(floor))
  return bands
    .map(([floor, symbol], i) => {
      if (!wholeNumbers) return `${symbol} ≥ ${format(floor)}`
      const ceiling = i === 0 ? 100 : (bands[i - 1]?.[0] ?? 100) - 1
      return ceiling > floor ? `${symbol} ${format(floor)}–${format(ceiling)}` : `${symbol} ${format(floor)}`
    })
    .join(" · ")
}
