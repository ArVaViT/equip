#!/usr/bin/env node
// WCAG contrast audit for semantic tokens in src/index.css.
// Parses :root and .dark blocks, computes contrast ratios for known pairs,
// flags any pair that falls below AA (4.5:1 for body text, 3:1 for large).
//
// Usage:
//   node scripts/contrast-audit.mjs                  # human-readable table
//   node scripts/contrast-audit.mjs --markdown       # markdown report

import { readFileSync } from "node:fs"
import { fileURLToPath } from "node:url"
import { dirname, resolve } from "node:path"

const __dirname = dirname(fileURLToPath(import.meta.url))
const cssPath = resolve(__dirname, "../src/index.css")
const css = readFileSync(cssPath, "utf8")

function parseBlock(blockName) {
  const re = new RegExp(`${blockName.replace(/\./g, "\\.")}\\s*\\{([\\s\\S]*?)\\n\\s*\\}`, "m")
  const match = re.exec(css)
  if (!match) throw new Error(`Could not find block ${blockName}`)
  const body = match[1]
  const tokens = {}
  for (const line of body.split("\n")) {
    const m = line.match(/^\s*--([\w-]+):\s*([^;]+);/)
    if (m) tokens[m[1]] = m[2].trim()
  }
  return tokens
}

function hslToRgb(h, s, l) {
  s /= 100
  l /= 100
  const k = (n) => (n + h / 30) % 12
  const a = s * Math.min(l, 1 - l)
  const f = (n) =>
    l - a * Math.max(-1, Math.min(k(n) - 3, Math.min(9 - k(n), 1)))
  return [f(0) * 255, f(8) * 255, f(4) * 255]
}

function parseHsl(str) {
  const m = str.match(/^(-?[\d.]+)\s+(-?[\d.]+)%\s+(-?[\d.]+)%$/)
  if (!m) throw new Error(`Could not parse HSL: ${str}`)
  return [parseFloat(m[1]), parseFloat(m[2]), parseFloat(m[3])]
}

function relativeLuminance([r, g, b]) {
  const norm = (c) => {
    c /= 255
    return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4)
  }
  return 0.2126 * norm(r) + 0.7152 * norm(g) + 0.0722 * norm(b)
}

function contrastRatio(hslA, hslB) {
  const lA = relativeLuminance(hslToRgb(...parseHsl(hslA)))
  const lB = relativeLuminance(hslToRgb(...parseHsl(hslB)))
  const [light, dark] = lA > lB ? [lA, lB] : [lB, lA]
  return (light + 0.05) / (dark + 0.05)
}

// Compose a translucent surface (foregroundToken at given alpha 0..1) over a
// solid base. We need this because Tailwind classes like `bg-muted/30` paint
// 30% of `--muted` on top of whatever is behind — the *effective* background
// is the alpha-blend, and that's what contrast must be measured against.
function composeHsl(overlayHsl, alpha, baseHsl) {
  const [or, og, ob] = hslToRgb(...parseHsl(overlayHsl))
  const [br, bg, bb] = hslToRgb(...parseHsl(baseHsl))
  const r = or * alpha + br * (1 - alpha)
  const g = og * alpha + bg * (1 - alpha)
  const b = ob * alpha + bb * (1 - alpha)
  return [r, g, b]
}

function contrastRatioRgb(rgbA, rgbB) {
  const lA = relativeLuminance(rgbA)
  const lB = relativeLuminance(rgbB)
  const [light, dark] = lA > lB ? [lA, lB] : [lB, lA]
  return (light + 0.05) / (dark + 0.05)
}

// Pairs we care about: [foreground token, background token, role, size]
// A `bgAlpha` entry means the background is `bgToken` painted at that alpha
// over `bgBase` (default: --background) — composited just like CSS does.
const PAIRS = [
  ["foreground", "background", "body text on page", "normal"],
  ["muted-foreground", "background", "captions on page", "normal"],
  ["muted-foreground", "muted", "captions on muted surface", "normal"],
  ["card-foreground", "card", "body on card", "normal"],
  ["popover-foreground", "popover", "body on popover", "normal"],
  ["primary-foreground", "primary", "label on primary button", "normal"],
  ["secondary-foreground", "secondary", "label on secondary button", "normal"],
  ["destructive-foreground", "destructive", "label on destructive button", "normal"],
  ["accent-foreground", "accent", "label on accent surface", "normal"],
  ["success-foreground", "success", "label on success", "normal"],
  ["warning-foreground", "warning", "label on warning", "normal"],
  ["info-foreground", "info", "label on info", "normal"],
  ["foreground", "muted", "body text on muted", "normal"],
  ["primary", "background", "primary text on page (links, accents)", "normal"],
  ["sidebar-foreground", "sidebar", "sidebar body text", "normal"],
  ["sidebar-accent-foreground", "sidebar-accent", "sidebar active item", "normal"],
  ["auth-panel-text", "auth-panel-bg", "auth panel body text", "normal"],
  ["auth-panel-text-muted", "auth-panel-bg", "auth panel caption", "normal"],
  // ----- Translucent overlay surfaces -----
  // Repeated in the codebase: `bg-muted/30`, `bg-muted/40`, `bg-muted/60`,
  // `bg-muted/15`, `bg-warning/10`, `bg-destructive/10`, `bg-primary/5`.
  // We check that body text and captions stay readable on the COMPOSITED
  // surface — not just on the solid token.
  { fg: "foreground", bg: "muted", bgAlpha: 0.3, role: "body text on bg-muted/30 over page", size: "normal" },
  { fg: "foreground", bg: "muted", bgAlpha: 0.4, role: "body text on bg-muted/40 over page", size: "normal" },
  { fg: "foreground", bg: "muted", bgAlpha: 0.6, role: "body text on bg-muted/60 over page", size: "normal" },
  { fg: "muted-foreground", bg: "muted", bgAlpha: 0.15, role: "caption on bg-muted/15 over page", size: "normal" },
  { fg: "muted-foreground", bg: "muted", bgAlpha: 0.3, role: "caption on bg-muted/30 over page", size: "normal" },
  { fg: "muted-foreground", bg: "muted", bgAlpha: 0.4, role: "caption on bg-muted/40 over page", size: "normal" },
  { fg: "foreground", bg: "warning", bgAlpha: 0.1, role: "body text on bg-warning/10 over page (pending banner)", size: "normal" },
  { fg: "foreground", bg: "destructive", bgAlpha: 0.1, role: "body text on bg-destructive/10 over page (error banner)", size: "normal" },
  { fg: "foreground", bg: "primary", bgAlpha: 0.05, role: "body text on bg-primary/5 over page (selected card)", size: "normal" },
  { fg: "foreground", bg: "primary", bgAlpha: 0.15, role: "label on bg-primary/15 over page (active toolbar button)", size: "normal" },
  // Card-context overlays (cards already paint solid --card under the wash).
  { fg: "foreground", bg: "muted", bgAlpha: 0.3, bgBase: "card", role: "body text on bg-muted/30 over card", size: "normal" },
  { fg: "muted-foreground", bg: "muted", bgAlpha: 0.15, bgBase: "card", role: "caption on bg-muted/15 over card", size: "normal" },
]

const THRESHOLDS = { normal: 4.5, large: 3 }

function normalizePair(p) {
  if (Array.isArray(p)) {
    const [fg, bg, role, size] = p
    return { fg, bg, role, size }
  }
  return p
}

function audit(themeName, tokens) {
  const rows = []
  let failures = 0
  for (const raw of PAIRS) {
    const { fg, bg, role, size, bgAlpha, bgBase } = normalizePair(raw)
    if (!(fg in tokens) || !(bg in tokens)) {
      rows.push({
        role,
        fg,
        bg: bgAlpha ? `${bg}/${Math.round(bgAlpha * 100)}` : bg,
        ratio: null,
        threshold: THRESHOLDS[size],
        pass: null,
        note: "token missing",
      })
      continue
    }
    let ratio
    let bgLabel = bg
    if (typeof bgAlpha === "number") {
      const baseToken = bgBase ?? "background"
      if (!(baseToken in tokens)) {
        rows.push({
          role,
          fg,
          bg: `${bg}/${Math.round(bgAlpha * 100)}`,
          ratio: null,
          threshold: THRESHOLDS[size],
          pass: null,
          note: `base ${baseToken} missing`,
        })
        continue
      }
      const composed = composeHsl(tokens[bg], bgAlpha, tokens[baseToken])
      const fgRgb = hslToRgb(...parseHsl(tokens[fg]))
      ratio = contrastRatioRgb(fgRgb, composed)
      bgLabel = `${bg}/${Math.round(bgAlpha * 100)} on --${baseToken}`
    } else {
      ratio = contrastRatio(tokens[fg], tokens[bg])
    }
    const threshold = THRESHOLDS[size]
    const pass = ratio >= threshold
    if (!pass) failures++
    rows.push({
      role,
      fg,
      bg: bgLabel,
      ratio: ratio.toFixed(2),
      threshold,
      pass,
      note: pass ? "" : `below AA ${size}`,
    })
  }
  return { themeName, rows, failures }
}

const lightTokens = parseBlock(":root")
const darkTokens = parseBlock(".dark")

const lightAudit = audit("light", lightTokens)
const darkAudit = audit("dark", darkTokens)

const isMarkdown = process.argv.includes("--markdown")

function renderTable({ themeName, rows, failures }) {
  if (isMarkdown) {
    let out = `\n### ${themeName} theme\n\n`
    out += `| Role | fg | bg | ratio | AA | status |\n`
    out += `|------|----|----|-------|----|--------|\n`
    for (const r of rows) {
      const status = r.pass === null ? "?" : r.pass ? "PASS" : "FAIL"
      out += `| ${r.role} | \`--${r.fg}\` | \`--${r.bg}\` | ${r.ratio ?? "—"} | ${r.threshold} | ${status} ${r.note} |\n`
    }
    out += `\n**${failures}** failure${failures === 1 ? "" : "s"} in ${themeName} theme.\n`
    return out
  }
  const lines = [`\n=== ${themeName} theme ===`]
  for (const r of rows) {
    const status = r.pass === null ? "?" : r.pass ? "PASS" : "FAIL"
    lines.push(
      `  [${status}] ${r.ratio ?? "—".padStart(5)} (need ${r.threshold}) — ${r.role}: --${r.fg} on --${r.bg} ${r.note}`,
    )
  }
  lines.push(`  ${failures} failure${failures === 1 ? "" : "s"} in ${themeName}.`)
  return lines.join("\n")
}

if (isMarkdown) {
  console.log("# WCAG contrast audit — semantic tokens\n")
  console.log(`Generated by \`frontend/scripts/contrast-audit.mjs\` from \`src/index.css\`.\n`)
  console.log(`AA thresholds: normal text ${THRESHOLDS.normal}, large text ${THRESHOLDS.large}.\n`)
  console.log(renderTable(lightAudit))
  console.log(renderTable(darkAudit))
} else {
  console.log(renderTable(lightAudit))
  console.log(renderTable(darkAudit))
}

const totalFailures = lightAudit.failures + darkAudit.failures
if (totalFailures > 0) {
  process.exitCode = 1
}
