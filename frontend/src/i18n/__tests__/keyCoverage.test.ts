/// <reference types="node" />
/**
 * Static check that every literal key passed to `t("...")` somewhere in the
 * source tree resolves in BOTH locale bundles. Dynamic keys (template literals
 * or string concatenation) are skipped — they can't be checked statically.
 *
 * This is the third layer of the bilingual-by-default guard:
 *   1. CI parity script (en.json vs ru.json keysets) — `i18n-check.mjs`
 *   2. missingKeyHandler that throws in test mode — `i18n/config.ts`
 *   3. THIS — guarantees a `t("foo.bar")` callsite without a corresponding
 *      JSON entry blows up at PR time, even if no other test happens to
 *      render the component.
 *
 * Plural-aware: a key may exist only as `key_one`/`key_other` in a two-form
 * language (en, de) or `key_one`/`key_few`/`key_many`/`key_other` in a
 * four-form one (ru, uk) — i18next resolves the base key at render time via
 * the active plural rule.
 *
 * Every served language is checked, not just the first two. A missing key
 * does not throw for the person reading in German any less than it does for
 * the person reading in Russian.
 */

import { describe, expect, it } from "vitest"
import { readdirSync, readFileSync, statSync } from "node:fs"
import { join, resolve, dirname } from "node:path"
import { fileURLToPath } from "node:url"
import en from "../locales/en.json"
import ru from "../locales/ru.json"
import de from "../locales/de.json"
import uk from "../locales/uk.json"

const __filename = fileURLToPath(import.meta.url)
const __dirname = dirname(__filename)
const srcDir = resolve(__dirname, "../..")

type Json = string | number | boolean | null | { [k: string]: Json } | Json[]

function flatten(obj: Json, prefix = "", out = new Set<string>()): Set<string> {
  if (obj && typeof obj === "object" && !Array.isArray(obj)) {
    for (const [k, v] of Object.entries(obj)) {
      flatten(v, prefix ? `${prefix}.${k}` : k, out)
    }
  } else {
    out.add(prefix)
  }
  return out
}

const TWO_FORM_SUFFIXES = ["_one", "_other"]
const FOUR_FORM_SUFFIXES = ["_one", "_few", "_many", "_other"]

/** Every language the platform serves, with the plural forms it uses. */
const BUNDLES: ReadonlyArray<{ locale: string; keys: Set<string>; suffixes: readonly string[] }> = [
  { locale: "en", keys: flatten(en as Json), suffixes: TWO_FORM_SUFFIXES },
  { locale: "ru", keys: flatten(ru as Json), suffixes: FOUR_FORM_SUFFIXES },
  { locale: "de", keys: flatten(de as Json), suffixes: TWO_FORM_SUFFIXES },
  { locale: "uk", keys: flatten(uk as Json), suffixes: FOUR_FORM_SUFFIXES },
]

function existsWithPlurals(key: string, set: Set<string>, suffixes: readonly string[]): boolean {
  if (set.has(key)) return true
  for (const suffix of suffixes) {
    if (set.has(`${key}${suffix}`)) return true
  }
  return false
}

const SKIP_DIRS = new Set([
  "node_modules",
  "dist",
  "build",
  "__tests__",
  "__mocks__",
  "test",
  "tests",
])
const SKIP_FILE_SUFFIXES = [".test.ts", ".test.tsx", ".spec.ts", ".spec.tsx"]

function walk(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    if (SKIP_DIRS.has(name)) continue
    const full = join(dir, name)
    const s = statSync(full)
    if (s.isDirectory()) {
      walk(full, out)
    } else if (s.isFile()) {
      if (!/\.(ts|tsx)$/.test(name)) continue
      if (SKIP_FILE_SUFFIXES.some((suffix) => name.endsWith(suffix))) continue
      out.push(full)
    }
  }
  return out
}

// Matches `t("foo.bar")`, `t('foo.bar')`, but NOT `t(\`foo.${x}\`)` or
// `t(variable)`. Word-boundary on `t` plus a leading non-alpha char so we
// don't accidentally capture other identifiers ending in `t` (e.g. `set`,
// `convert`). Backticks not allowed inside the captured key — even though
// `t(\`literal\`)` would resolve correctly, projects usually mean to use a
// plain string and grepping for backticks would also pick up interpolation.
const T_CALL_PATTERN = /(?<![A-Za-z_$])t\(\s*["']([^"']+)["']/g

const sourceFiles = walk(srcDir)
const usedKeys = new Set<string>()
for (const file of sourceFiles) {
  const content = readFileSync(file, "utf8")
  for (const match of content.matchAll(T_CALL_PATTERN)) {
    const key = match[1]
    if (key) usedKeys.add(key)
  }
}

describe("i18n key coverage", () => {
  it("scans a reasonable number of source files and finds t() calls", () => {
    // Guard against the test silently passing because the walk found nothing
    // (e.g. due to a bad path or stale fixture).
    expect(sourceFiles.length).toBeGreaterThan(50)
    expect(usedKeys.size).toBeGreaterThan(50)
  })

  it.each(BUNDLES.map((b) => [b.locale, b] as const))(
    "every literal t() key resolves in %s.json (or its plural variants)",
    (locale, bundle) => {
      const missing: string[] = []
      for (const key of usedKeys) {
        if (!existsWithPlurals(key, bundle.keys, bundle.suffixes)) missing.push(key)
      }
      if (missing.length > 0) {
        missing.sort()
        throw new Error(
          `Missing in ${locale}.json:\n${missing.map((k) => `  ${k}`).join("\n")}\n` +
            `(${missing.length} key${missing.length === 1 ? "" : "s"})`,
        )
      }
    },
  )
})
