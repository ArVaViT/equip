#!/usr/bin/env node
// Upload Vite source maps to Datadog so RUM stack traces resolve to
// real file names and line numbers. Runs after `vite build`. Silently
// skips when DATADOG_API_KEY isn't set so local builds still work.

import { spawnSync } from 'node:child_process'
import { existsSync } from 'node:fs'

if (!process.env.DATADOG_API_KEY) {
  console.log('[sourcemaps] DATADOG_API_KEY not set, skipping upload (local build)')
  process.exit(0)
}

if (!existsSync('dist/assets')) {
  console.log('[sourcemaps] dist/assets not found, skipping')
  process.exit(0)
}

const version =
  process.env.VITE_APP_VERSION ||
  (process.env.VERCEL_GIT_COMMIT_SHA ? process.env.VERCEL_GIT_COMMIT_SHA.slice(0, 7) : 'dev')

const args = [
  'datadog-ci',
  'sourcemaps',
  'upload',
  'dist/assets',
  '--service',
  'equip-frontend',
  '--release-version',
  version,
  '--minified-path-prefix',
  'https://equipbible.com/assets',
]

console.log(`[sourcemaps] uploading version=${version}`)
const result = spawnSync('npx', args, { stdio: 'inherit', shell: true })
process.exit(result.status ?? 1)
