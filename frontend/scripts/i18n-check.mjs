#!/usr/bin/env node
// Key-parity check for locale bundles.
//
// English is the reference: every key it has must exist in every other
// bundle, and no bundle may carry a key English does not have — except the
// extra plural forms some languages need. i18next strips the suffix when it
// resolves, so `quiz.nQuestions_few` on the Russian side answers to the same
// base key as English's `_one` / `_other`.
//
// Plural categories per language (CLDR):
//   en, de   — one, other
//   ru, uk   — one, few, many, other
//
// This used to compare en.json against ru.json and nothing else, which meant
// German and Ukrainian could drift silently the day they shipped.
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

const REFERENCE = "en"
const TARGETS = ["ru", "de", "uk"]

function load(locale) {
  const path = resolve(__dirname, `../src/i18n/locales/${locale}.json`)
  return JSON.parse(readFileSync(path, "utf8"))
}

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

// Plural suffixes a target language may add on top of what English carries.
const EXTRA_PLURAL_SUFFIXES = ["_few", "_many", "_zero", "_two"]

function stripPluralSuffix(key) {
  for (const suffix of EXTRA_PLURAL_SUFFIXES) {
    if (key.endsWith(suffix)) return key.slice(0, -suffix.length)
  }
  return null
}

const enFlat = flatten(load(REFERENCE))
const emptyValues = []
for (const [key, value] of enFlat) {
  if (typeof value === "string" && value.trim() === "") emptyValues.push([REFERENCE, key])
}

const results = {}
for (const locale of TARGETS) {
  const flat = flatten(load(locale))
  const missing = []
  const extra = []

  for (const key of enFlat.keys()) {
    if (!flat.has(key)) missing.push(key)
  }

  for (const [key, value] of flat) {
    if (typeof value === "string" && value.trim() === "") emptyValues.push([locale, key])
    if (enFlat.has(key)) continue
    const stripped = stripPluralSuffix(key)
    if (stripped && enFlat.has(stripped)) continue
    if (stripped && (enFlat.has(`${stripped}_one`) || enFlat.has(`${stripped}_other`))) continue
    extra.push(key)
  }

  results[locale] = { count: flat.size, missing, extra }
}

const wantJson = process.argv.includes("--json")
const ok =
  emptyValues.length === 0 &&
  TARGETS.every((locale) => results[locale].missing.length === 0 && results[locale].extra.length === 0)

if (wantJson) {
  process.stdout.write(
    JSON.stringify({ ok, reference: REFERENCE, enCount: enFlat.size, locales: results, emptyValues }, null, 2) + "\n",
  )
} else {
  console.log(`${REFERENCE}.json: ${enFlat.size} keys (reference)`)
  for (const locale of TARGETS) {
    console.log(`${locale}.json: ${results[locale].count} keys`)
  }
  console.log("")

  for (const locale of TARGETS) {
    const { missing, extra } = results[locale]
    if (missing.length > 0) {
      console.log(`❌ ${missing.length} EN key(s) missing from ${locale}.json:`)
      for (const k of missing) console.log(`   ${k}`)
      console.log("")
    }
    if (extra.length > 0) {
      console.log(`❌ ${extra.length} ${locale.toUpperCase()} key(s) with no matching EN key (and not a plural variant):`)
      for (const k of extra) console.log(`   ${k}`)
      console.log("")
    }
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
