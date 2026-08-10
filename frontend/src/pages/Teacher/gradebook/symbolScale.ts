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
 * Tones from best to worst, indexed directly rather than derived from a
 * fraction. The fraction version bucketed `index / (n - 1)` against fixed
 * cutoffs and gave two adjacent bands the same colour as soon as a school
 * defined six.
 *
 * The palette is finite, so a scale longer than it must repeat somewhere. It
 * repeats the *lowest* passing tone, never a higher one: running out of
 * colours must not paint a low grade to look better than it is. That
 * monotonicity is the property under test — "every band gets its own colour"
 * is impossible past five and was the wrong thing to ask for.
 */
const TONES = [
  "bg-success/15 text-success",
  "bg-info/15 text-info",
  "bg-accent/20 text-ink",
  "bg-warning/15 text-warning",
] as const

const FAILING_TONE = "bg-destructive/15 text-destructive"
const UNKNOWN_TONE = "bg-muted text-ink-muted"

/**
 * Colour by position in the scale rather than by name, so «5» reads like «A»
 * and «2» like «F» without anybody maintaining a second table.
 *
 * The bottom band is the failing one in every scheme that has bands, so it
 * always takes the failing tone; the rest walk down the list above and repeat
 * its last entry if a school defines more bands than there are tones. Repeating
 * the *lowest* passing tone is deliberate: running out of colours must never
 * promote a low grade into a higher-looking one.
 */
export function symbolTone(symbol: string, bands: GradeBand[]): string {
  const rank = symbolRank(symbol, bands)
  if (rank === -1 || bands.length === 0) return UNKNOWN_TONE

  const fromTop = bands.length - rank
  if (fromTop === bands.length - 1) return FAILING_TONE
  return TONES[Math.min(fromTop, TONES.length - 1)] ?? UNKNOWN_TONE
}
