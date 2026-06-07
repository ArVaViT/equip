#!/usr/bin/env node
// Delete Vite source maps after they've been uploaded to Datadog, so the
// `.map` files (full original TS source) are NEVER served publicly from
// Vercel. `vite.config.ts` uses `sourcemap: 'hidden'` (no sourceMappingURL
// trailer), but the files are still fetchable by URL at
// `https://equipbible.com/assets/<chunk>.js.map` unless removed.
// Datadog already has its copy (see upload-sourcemaps.mjs), so deleting them
// here costs nothing and closes the source-disclosure hole.

import { existsSync, readdirSync, rmSync } from 'node:fs'
import { join } from 'node:path'

const dir = 'dist/assets'
if (!existsSync(dir)) {
  console.log('[sourcemaps] dist/assets not found, nothing to delete')
  process.exit(0)
}

const maps = readdirSync(dir).filter((f) => f.endsWith('.map'))
for (const f of maps) rmSync(join(dir, f), { force: true })
console.log(`[sourcemaps] deleted ${maps.length} .map file(s) from ${dir} (not shipped to Vercel)`)
