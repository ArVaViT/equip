#!/usr/bin/env node
// Bundle-size sentinel — runs after ``vite build`` and fails the build
// when any JS chunk grows past the per-chunk budget.
//
// Why per-chunk thresholds instead of one total: each chunk maps to a
// specific surface (ChapterEditor = teacher rich-text editor lazy load,
// index = always-on shell). Regressions usually land in ONE chunk
// because someone import-ed a heavy lib into one route — a per-chunk
// gate catches that on the next PR build, a total-bytes gate would
// silently let it grow until cumulative drift forces a panicked
// optimisation pass.
//
// Budgets are anchored to current size + ~15% headroom so day-to-day
// editor refactors don't trip the gate. Bump deliberately and document
// the reason in the commit message when a chunk legitimately grows.

import { readdir, stat } from "node:fs/promises";
import { join } from "node:path";

const DIST = join(process.cwd(), "dist", "assets");

// Per-chunk gzip-budgeted ceilings, in kB. We assert on **gzip** size
// because that's what the browser actually downloads — minified-but-
// uncompressed size is misleading. Numbers reflect the 2026-06-03
// baseline + ~15% headroom.
const BUDGETS_GZIP_KB = {
  index: 200, // shell — always loaded; main app router + Datadog RUM init.
  ChapterEditor: 340, // teacher TipTap surface; lazy-loaded per /teacher/courses route.
  ChapterView: 100, // student chapter render (DOMPurify + i18n).
  vendor: 80, // React + react-router + a few small libs.
  supabase: 70, // supabase-js v2 client; could be split if it grows further.
  config: 60, // i18next config + bundled namespaces.
  "dnd.esm": 35, // @hello-pangea/dnd ESM build.
  schemas: 22, // zod schemas (shared across forms).
};

// Vite chunk filenames look like ``<name>-<hash>.js``. The name can
// contain dots (e.g. ``dnd.esm-DcITUONc.js``), so we split on the
// last hyphen and treat everything before it as the chunk name.
function chunkPrefix(filename) {
  if (!filename.endsWith(".js")) return null;
  const stem = filename.slice(0, -3);
  const lastDash = stem.lastIndexOf("-");
  if (lastDash <= 0) return null;
  const name = stem.slice(0, lastDash);
  const hash = stem.slice(lastDash + 1);
  // Sanity: the hash part should be at least 6 chars of alphanumerics.
  if (!/^[A-Za-z0-9_-]{6,}$/.test(hash)) return null;
  return name;
}

async function gzipSizeKb(path) {
  // Vite emits an adjacent ``<file>.gz`` only when compress plugin is
  // configured — we don't, so compute via Node's zlib.
  const { gzip } = await import("node:zlib");
  const { readFile } = await import("node:fs/promises");
  const { promisify } = await import("node:util");
  const buf = await readFile(path);
  const gz = await promisify(gzip)(buf);
  return gz.byteLength / 1024;
}

async function main() {
  let files;
  try {
    files = await readdir(DIST);
  } catch (err) {
    console.error(`fatal: cannot read ${DIST} — did you run \`npm run build\` first?`);
    console.error(String(err));
    process.exitCode = 1;
    return;
  }
  const violations = [];
  // A budget name can match more than one emitted file (e.g. the
  // ``supabase`` manual chunk plus a tiny same-named import facade).
  // Collect every match per budget first, then assert on the LARGEST —
  // that's the real payload; the facade would otherwise shadow it.
  const matchesByPrefix = new Map();
  for (const f of files) {
    if (!f.endsWith(".js")) continue;
    const prefix = chunkPrefix(f);
    if (prefix === null) continue;
    const budget = BUDGETS_GZIP_KB[prefix];
    if (budget === undefined) continue;
    const path = join(DIST, f);
    const st = await stat(path);
    if (!st.isFile()) continue;
    const gz = await gzipSizeKb(path);
    if (!matchesByPrefix.has(prefix)) matchesByPrefix.set(prefix, []);
    matchesByPrefix.get(prefix).push({ prefix, file: f, gz, budget });
  }
  const checked = [];
  for (const [prefix, matches] of matchesByPrefix) {
    matches.sort((a, b) => b.gz - a.gz);
    const largest = matches[0];
    if (matches.length > 1) {
      console.warn(
        `warn: budget "${prefix}" matched ${matches.length} files ` +
          `(${matches.map((m) => m.file).join(", ")}); asserting on the largest.`,
      );
    }
    checked.push(largest);
    if (largest.gz > largest.budget) {
      violations.push(largest);
    }
  }
  // Always print the budget table so reviewers see headroom at a glance.
  console.log("\nBundle-size sentinel (gzip kB):");
  console.log("  " + "chunk".padEnd(16) + "actual".padStart(10) + "  /  " + "budget".padEnd(10));
  for (const c of checked.sort((a, b) => b.gz - a.gz)) {
    const flag = c.gz > c.budget ? " ✗" : "";
    console.log(
      "  " +
        c.prefix.padEnd(16) +
        c.gz.toFixed(1).padStart(10) +
        "  /  " +
        c.budget.toFixed(0).padEnd(10) +
        flag,
    );
  }
  if (violations.length > 0) {
    console.error(
      "\nFAIL — these chunks exceed their gzip budget:",
      JSON.stringify(violations, null, 2),
    );
    console.error(
      "\nIf the growth is intentional, bump the matching BUDGETS_GZIP_KB " +
        "entry in scripts/check-bundle-size.mjs IN THE SAME PR and explain " +
        "why in the commit message.",
    );
    process.exitCode = 1;
    return;
  }
  console.log("\nOK — all chunks within budget.\n");
}

main().catch((err) => {
  console.error("Unexpected sentinel error:", err);
  process.exitCode = 1;
});
