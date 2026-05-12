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
 * Plural-aware: a key may exist only as `key_one`/`key_other` on the EN side
 * or `key_one`/`key_few`/`key_many`/`key_other` on the RU side — i18next
 * resolves the base key at render time via the active plural rule.
 */

import { describe, expect, it } from "vitest"
import { readdirSync, readFileSync, statSync } from "node:fs"
import { join, resolve, dirname } from "node:path"
import { fileURLToPath } from "node:url"
import en from "../locales/en.json"
import ru from "../locales/ru.json"

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

const enKeys = flatten(en as Json)
const ruKeys = flatten(ru as Json)

const EN_PLURAL_SUFFIXES = ["_one", "_other"]
const RU_PLURAL_SUFFIXES = ["_one", "_few", "_many", "_other"]

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

  it("every literal t() key resolves in en.json (or its plural variants)", () => {
    const missing: string[] = []
    for (const key of usedKeys) {
      if (!existsWithPlurals(key, enKeys, EN_PLURAL_SUFFIXES)) missing.push(key)
    }
    if (missing.length > 0) {
      missing.sort()
      throw new Error(
        `Missing in en.json:\n${missing.map((k) => `  ${k}`).join("\n")}\n` +
          `(${missing.length} key${missing.length === 1 ? "" : "s"})`,
      )
    }
  })

  it("every literal t() key resolves in ru.json (or its plural variants)", () => {
    const missing: string[] = []
    for (const key of usedKeys) {
      if (!existsWithPlurals(key, ruKeys, RU_PLURAL_SUFFIXES)) missing.push(key)
    }
    if (missing.length > 0) {
      missing.sort()
      throw new Error(
        `Missing in ru.json:\n${missing.map((k) => `  ${k}`).join("\n")}\n` +
          `(${missing.length} key${missing.length === 1 ? "" : "s"})`,
      )
    }
  })
})
