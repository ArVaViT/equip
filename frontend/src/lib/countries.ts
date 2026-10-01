/**
 * Countries for the profile, named in the reader's language by the browser
 * (`Intl.DisplayNames`) — no list of names to translate or keep current.
 *
 * The codes are what `Intl` knows as regions, minus the ones that are not a
 * place a person lives: groupings (EU, UN, Eurozone), pseudo-locales, the
 * "unknown" region, and territories outside ISO 3166-1 that only exist for
 * tagging (Ceuta and Melilla, Canary Islands…). Stored upper case, as the
 * `profiles_country_code_check` constraint requires.
 */
const NOT_A_COUNTRY = new Set(["AC", "CP", "DG", "EA", "EU", "EZ", "IC", "QO", "TA", "UN", "XA", "XB", "ZZ"])

let codesCache: string[] | null = null

export function countryCodes(): string[] {
  if (codesCache) return codesCache
  const out: string[] = []
  try {
    const names = new Intl.DisplayNames("en", { type: "region", fallback: "none" })
    const letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    for (const a of letters) {
      for (const b of letters) {
        const code = a + b
        if (!NOT_A_COUNTRY.has(code) && names.of(code)) out.push(code)
      }
    }
  } catch {
    // An engine without DisplayNames: the field falls back to showing codes.
  }
  codesCache = out
  return out
}

export function countryName(code: string, locale: string): string {
  try {
    return new Intl.DisplayNames(locale, { type: "region" }).of(code) ?? code
  } catch {
    return code
  }
}

/** Codes sorted by their name in `locale`, for a select. */
export function countriesSorted(locale: string): { code: string; name: string }[] {
  const collator = new Intl.Collator(locale)
  return countryCodes()
    .map((code) => ({ code, name: countryName(code, locale) }))
    .sort((x, y) => collator.compare(x.name, y.name))
}
