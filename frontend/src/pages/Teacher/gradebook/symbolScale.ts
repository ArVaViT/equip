/** A band as the backend sends it: `[floor, symbol]`, highest floor first. */
export type GradeBand = [number, string]

/**
 * Rank and colour for a grade symbol, read from the school's own bands.
 *
 * The client used to keep a private copy of the A–F scale in two places — an
 * ordering table and a colour switch — and `grading_scheme.py` names that
 * duplication in a comment. It was harmless only because every course on the
 * platform happens to use letters. The moment a school picks the five-point
 * scheme, that copy makes «5» sort equal to «2» (both unknown, both zero) and
 * paints every grade the same grey, while the numbers themselves stay right.
 * Nothing looks broken; the sort just quietly stops meaning anything.
 *
 * The backend already returns the bands on the scheme endpoint. Reading them is
 * both less code and the only version that survives a school editing its scale.
 */

/** Higher is better. Unknown symbols sort below everything, not equal to it. */
export function symbolRank(symbol: string, bands: GradeBand[]): number {
  // Bands arrive highest-floor-first, so position is rank: the first entry is
  // the top grade whatever it is called.
  const index = bands.findIndex(([, s]) => s === symbol)
  return index === -1 ? -1 : bands.length - index
}

/**
 * Colour by position in the scale rather than by name, so «5» reads like «A»
 * and «2» like «F» without anybody maintaining a second table.
 */
export function symbolTone(symbol: string, bands: GradeBand[]): string {
  const rank = symbolRank(symbol, bands)
  if (rank === -1 || bands.length === 0) return "bg-muted text-ink-muted"

  // Position from the top, as a fraction — a four-band scale and a five-band
  // one both map onto the same five tones without special-casing either.
  const fromTop = (bands.length - rank) / Math.max(1, bands.length - 1)
  if (fromTop <= 0.01) return "bg-success/15 text-success"
  if (fromTop <= 0.34) return "bg-info/15 text-info"
  if (fromTop <= 0.67) return "bg-accent/20 text-ink"
  if (fromTop < 1) return "bg-warning/15 text-warning"
  // The bottom band is the failing one in every scheme that has bands.
  return "bg-destructive/15 text-destructive"
}
