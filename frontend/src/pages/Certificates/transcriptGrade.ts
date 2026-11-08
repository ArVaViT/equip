import { formatGradePercent } from "@/pages/Teacher/gradebook/formatGrade"
import type { Certificate } from "@/types"

/** The language of the document: English, whatever the interface speaks. */
export const DOCUMENT_LOCALE = "en-GB"

/** Schemes whose grade is a symbol a reader could mistake for another scale's. */
const SYMBOL_SCHEMES = ["letter", "five_point"] as const
type SymbolScheme = (typeof SYMBOL_SCHEMES)[number]

function isSymbolScheme(scheme: string | null | undefined): scheme is SymbolScheme {
  return (SYMBOL_SCHEMES as readonly string[]).includes(scheme ?? "")
}

/** Literal keys, so the key-coverage check can see them. */
const SCHEME_NAME_KEY: Record<SymbolScheme, string> = {
  letter: "certificates.transcript.schemeName.letter",
  five_point: "certificates.transcript.schemeName.five_point",
}

const FIVE_POINT_WORD_KEY: Record<string, string> = {
  "5": "certificates.transcript.fivePoint.5",
  "4": "certificates.transcript.fivePoint.4",
  "3": "certificates.transcript.fivePoint.3",
  "2": "certificates.transcript.fivePoint.2",
}

export interface TranscriptGrade {
  /** What the grade cell says — «A», «5 (excellent)», «88%», «Pass», «Completed». */
  text: string
  /** The scheme the grade is read in, when it is a symbol; else `null`. */
  symbolScheme: SymbolScheme | null
}

/**
 * The grade a certificate was issued on, in the document's words.
 *
 * Read straight off the snapshot frozen at issuance (M6); nothing here
 * recomputes. A certificate with no recorded grade — issued on completion, or
 * before the platform kept grades on certificates — says «Completed», which is
 * exactly what it certifies.
 */
export function transcriptGrade(cert: Certificate, t: (key: string) => string): TranscriptGrade {
  const completed = { text: t("certificates.transcript.completedOnly"), symbolScheme: null }
  if (!cert.grading_scheme || cert.graded_via === "completion") return completed
  // An issued pass/fail certificate is a pass; its percentage is not the result (D2).
  if (cert.grading_scheme === "pass_fail") return { text: t("certificates.transcript.pass"), symbolScheme: null }
  if (cert.official_code) {
    const code = cert.official_code
    if (cert.grading_scheme === "five_point" && FIVE_POINT_WORD_KEY[code]) {
      return { text: `${code} (${t(FIVE_POINT_WORD_KEY[code])})`, symbolScheme: "five_point" }
    }
    return { text: code, symbolScheme: isSymbolScheme(cert.grading_scheme) ? cert.grading_scheme : null }
  }
  if (cert.official_score !== null && cert.official_score !== undefined) {
    return { text: formatGradePercent(Number(cert.official_score), DOCUMENT_LOCALE), symbolScheme: null }
  }
  return completed
}

/**
 * The scale most of this transcript's grades are in — the one the footnote
 * names once, so only the exceptions need a mark of their own. `null` when no
 * row carries a symbol.
 */
export function mainSymbolScheme(grades: TranscriptGrade[]): SymbolScheme | null {
  const counts = new Map<SymbolScheme, number>()
  for (const g of grades) if (g.symbolScheme) counts.set(g.symbolScheme, (counts.get(g.symbolScheme) ?? 0) + 1)
  let best: SymbolScheme | null = null
  for (const scheme of SYMBOL_SCHEMES) {
    if ((counts.get(scheme) ?? 0) > (best ? (counts.get(best) ?? 0) : 0)) best = scheme
  }
  return best
}

export function schemeName(scheme: SymbolScheme, t: (key: string) => string): string {
  return t(SCHEME_NAME_KEY[scheme])
}
