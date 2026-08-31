#!/usr/bin/env node
// Builds public/og-image.jpg — the card every unfurler (Telegram, Slack,
// Facebook, X) shows when somebody shares a link to the site.
//
// It is generated rather than drawn because the words on it are the landing
// page's own: the headline comes straight out of ru.json, so the card cannot
// quietly start promising something the site no longer says. Re-run after
// editing `landing.hero.manifesto`.
//
// The previous card was the cover image from a dev.to article — a blue book
// glyph on a blue gradient, wordless, from two palettes ago.
//
// Colours are the live design tokens (src/index.css):
//   paper  hsl(40 12% 97%)  #F8F8F6
//   ink    hsl(30 8% 11%)   #1E1C1A
//   muted  hsl(35 7% 40%)   #6D675F
//   sage   hsl(133 17% 37%) #4E6E55
//
// Usage: node scripts/build-og-image.mjs

import { readFileSync, writeFileSync } from "node:fs"
import { fileURLToPath } from "node:url"
import { dirname, resolve } from "node:path"
import { chromium } from "@playwright/test"

/* The two `page.evaluate` bodies below run inside Chromium, not in Node, so
   they legitimately reach for browser globals that this file otherwise has no
   business knowing about. Declared narrowly rather than by widening the
   `scripts/**` ESLint zone to include every browser global. */
/* global document, getComputedStyle */

const __dirname = dirname(fileURLToPath(import.meta.url))
export const OUT_FILE = resolve(__dirname, "../public/og-image.jpg")

// The dimensions declared in index.html's og:image:width / og:image:height.
// Rendered 1:1 rather than at 2x: a file twice the declared size is a claim
// the markup does not make, and 1200x630 is already past every unfurler's
// display size.
const WIDTH = 1200
const HEIGHT = 630

function copy() {
  const ru = JSON.parse(readFileSync(resolve(__dirname, "../src/i18n/locales/ru.json"), "utf8"))
  return {
    // Broken where the landing page breaks it, so the two read alike.
    manifesto: ru.landing.hero.manifesto.replace(/,\s+/, ",<br>"),
    name: "Equip",
    meta: ["Курсы", "Тесты", "Сертификаты"],
    domain: "equipbible.com",
  }
}

export function html() {
  const { manifesto, name, meta, domain } = copy()
  const [first, second, third] = meta
  return `<!doctype html>
<html lang="ru"><head><meta charset="utf-8">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Literata:opsz,wght@7..72,400;7..72,600&family=Golos+Text:wght@400;500&display=swap" rel="stylesheet">
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { width: ${WIDTH}px; height: ${HEIGHT}px; background: #F8F8F6; color: #1E1C1A;
         font-family: "Golos Text", system-ui, sans-serif; }
  .page { padding: 88px 96px; height: 100%; display: flex; flex-direction: column;
          justify-content: space-between; }
  .top { display: flex; align-items: center; gap: 22px; }
  .rule { width: 64px; height: 2px; background: #1E1C1A; }
  .name { font-size: 23px; letter-spacing: 0.26em; text-transform: uppercase; font-weight: 500; }
  .manifesto { font-family: Literata, Georgia, serif; font-weight: 600; font-size: 66px;
               line-height: 1.16; letter-spacing: -0.022em; max-width: 1010px; }
  .foot { display: flex; align-items: baseline; justify-content: space-between; }
  .meta { font-size: 21px; letter-spacing: 0.2em; text-transform: uppercase; color: #6D675F;
          font-weight: 500; }
  .domain { font-family: Literata, Georgia, serif; font-size: 25px; }
  .sage { color: #4E6E55; }
</style></head>
<body><div class="page">
  <div class="top"><div class="rule"></div><div class="name">${name}</div></div>
  <div class="manifesto">${manifesto}</div>
  <div class="foot">
    <div class="meta">${first} · ${second} · <span class="sage">${third}</span></div>
    <div class="domain">${domain}</div>
  </div>
</div></body></html>`
}

const browser = await chromium.launch()
const page = await (await browser.newContext({
  viewport: { width: WIDTH, height: HEIGHT },
  deviceScaleFactor: 1,
})).newPage()
await page.setContent(html(), { waitUntil: "networkidle" })
await page.evaluate(() => document.fonts.ready)
// The webfonts arrive over the network; a shot taken before they land is the
// fallback serif, which is not the product's face.
await page.waitForTimeout(1000)
const lines = await page.evaluate(() => {
  const el = document.querySelector(".manifesto")
  return Math.round(el.getBoundingClientRect().height / parseFloat(getComputedStyle(el).lineHeight))
})
if (lines !== 2) {
  console.warn(`⚠ headline set on ${lines} lines, not 2 — check the size/measure in this file`)
}
const buffer = await page.screenshot({ type: "jpeg", quality: 90 })
writeFileSync(OUT_FILE, buffer)
await browser.close()
console.log(`og-image.jpg written: ${WIDTH}x${HEIGHT}, ${(buffer.length / 1024).toFixed(1)} KB, headline on ${lines} lines`)
