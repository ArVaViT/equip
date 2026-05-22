#!/usr/bin/env node
// Key-parity check for locale bundles.
//
// Flattens en.json + ru.json into dot-paths, then verifies that every English
// key has a Russian counterpart. Russian-only `_few`/`_many` suffixed keys are
// allowed (Russian has 3 plural categories, English has 2 — i18next requires
// the extra forms on the Russian side).
//
// Exit codes:
//   0 — locales in parity
//   1 — drift detected (CI should fail)
//
// Usage:
//   node scripts/i18n-check.mjs            # human-readable
//   node scripts/i18n-check.mjs --json     # machine-readable

import { readFileSync } from "node:fs"
import { fileURLToPath } from "node:url"
import { dirname, resolve } from "node:path"

const __dirname = dirname(fileURLToPath(import.meta.url))
const enPath = resolve(__dirname, "../src/i18n/locales/en.json")
const ruPath = resolve(__dirname, "../src/i18n/locales/ru.json")

const en = JSON.parse(readFileSync(enPath, "utf8"))
const ru = JSON.parse(readFileSync(ruPath, "utf8"))

function flatten(obj, prefix = "", out = new Map()) {
  for (const [k, v] of Object.entries(obj)) {
    const path = prefix ? `${prefix}.${k}` : k
    if (v && typeof v === "object" && !Array.isArray(v)) {
      flatten(v, path, out)
    } else {
      out.set(path, v)
    }
  }
  return out
}

const enFlat = flatten(en)
const ruFlat = flatten(ru)

// Russian plural suffixes that English doesn't need. i18next strips the suffix
// when resolving, so e.g. "quiz.nQuestions_few" on the ru side maps back to
// the same base key as English's "quiz.nQuestions_one"/"_other".
const RU_ONLY_SUFFIXES = ["_few", "_many"]

function stripPluralSuffix(key) {
  for (const suffix of RU_ONLY_SUFFIXES) {
    if (key.endsWith(suffix)) return key.slice(0, -suffix.length)
  }
  return null
}

const missingInRu = []      // EN keys with no RU counterpart
const extraInRu = []        // RU keys with no EN counterpart (and not a plural variant of an existing EN key)
const emptyValues = []      // values that are empty strings

for (const [key, value] of enFlat) {
  if (typeof value === "string" && value.trim() === "") emptyValues.push(["en", key])
  if (!ruFlat.has(key)) missingInRu.push(key)
}

for (const [key, value] of ruFlat) {
  if (typeof value === "string" && value.trim() === "") emptyValues.push(["ru", key])
  if (enFlat.has(key)) continue
  const stripped = stripPluralSuffix(key)
  if (stripped && enFlat.has(stripped)) continue
  // Also allow if the stripped form exists with `_one` or `_other` suffix on EN side
  if (stripped) {
    const enOne = `${stripped}_one`
    const enOther = `${stripped}_other`
    if (enFlat.has(enOne) || enFlat.has(enOther)) continue
  }
  extraInRu.push(key)
}

const wantJson = process.argv.includes("--json")
const ok = missingInRu.length === 0 && extraInRu.length === 0 && emptyValues.length === 0

if (wantJson) {
  process.stdout.write(
    JSON.stringify(
      { ok, enCount: enFlat.size, ruCount: ruFlat.size, missingInRu, extraInRu, emptyValues },
      null,
      2,
    ) + "\n",
  )
} else {
  console.log(`en.json: ${enFlat.size} keys`)
  console.log(`ru.json: ${ruFlat.size} keys`)
  console.log("")

  if (missingInRu.length > 0) {
    console.log(`❌ ${missingInRu.length} EN key(s) missing from ru.json:`)
    for (const k of missingInRu) console.log(`   ${k}`)
    console.log("")
  }

  if (extraInRu.length > 0) {
    console.log(`❌ ${extraInRu.length} RU key(s) with no matching EN key (and not a plural variant):`)
    for (const k of extraInRu) console.log(`   ${k}`)
    console.log("")
  }

  if (emptyValues.length > 0) {
    console.log(`❌ ${emptyValues.length} empty value(s):`)
    for (const [locale, k] of emptyValues) console.log(`   [${locale}] ${k}`)
    console.log("")
  }

  if (ok) {
    console.log("✓ Locale bundles in parity.")
  } else {
    console.log("Locale drift detected — fix before merging.")
  }
}

process.exit(ok ? 0 : 1)
