#!/usr/bin/env node
/*
 * Bundle-size sentinel. Runs as part of `npm run build`, after `vite build`,
 * and fails the build when the shipped JS drifts from what we agreed to ship.
 *
 * Why per-chunk ceilings instead of one total: each chunk maps to a surface
 * (ChapterEditor = the teacher's rich-text editor, loaded lazily; index = the
 * always-on shell). A regression usually lands in ONE chunk because somebody
 * imported a heavy library into one route — a per-chunk gate names the chunk
 * on the next PR build, where a total-bytes gate would absorb it until
 * cumulative drift forces a panicked optimisation pass.
 *
 * The rules live in `bundle-budget.mjs` so they can be unit-tested; this file
 * is the IO around them. See that file for what the four verdicts mean.
 *
 * BUDGETS ARE ANCHORED TO MEASURED SIZE + ~15%. That is not decoration: a
 * budget far above the real number gates nothing, so the sentinel now fails
 * on a stale budget exactly as it fails on a regression. When a chunk
 * legitimately grows or shrinks, move its number IN THE SAME PR and say why
 * in the commit message.
 */

import { readdir, stat, readFile } from "node:fs/promises";
import { join } from "node:path";
import { gzip } from "node:zlib";
import { promisify } from "node:util";
import { chunkPrefix, evaluate, explain, UNBUDGETED_LIMIT_KB } from "./bundle-budget.mjs";

const DIST = join(process.cwd(), "dist", "assets");
const gzipAsync = promisify(gzip);

// Per-chunk gzip ceilings, in kB — gzip because that is what the browser
// downloads; minified-but-uncompressed size is misleading. Measured
// 2026-09-14 against the production build, plus ~15% headroom.
//
// Re-measured for vite 8.3 / rolldown 1.2, which consolidates chunks far
// more aggressively than 8.2 did. Judge that by first-load weight, not by
// any single chunk: the entry page went from 49 chunks / 337.2 kB gzip to
// 24 chunks / 330.7 kB. Slightly lighter, half the requests — so the growth
// of `index` below is consolidation, not a regression, and the numbers move
// to match. Nothing was added to the shell that a visitor did not already
// download under 8.2.
const BUDGETS_GZIP_KB = {
  ChapterEditor: 252, // teacher TipTap surface; lazy per /teacher/courses.
  LandingBackdrop: 147, // WebGL for the landing page's one background scene.
  //           Larger than the shell, and deliberate: `lazy()`-imported from
  //           PublicLanding alone, never mounted under
  //           `prefers-reduced-motion` or without WebGL, and its loop stops
  //           while the document is hidden. A student opening a lesson never
  //           fetches a byte of it — if this name appears in a route a
  //           signed-in user reaches, that is the bug, not the size.
  //
  //           The name tracks the importer: with two scenes importing
  //           `three` Rollup emitted a shared `three.module` chunk; with one
  //           it names the chunk after the component. Worth knowing, because
  //           the sentinel fails loudly either way — once for an unwatched
  //           chunk, once for a budget pointing at a chunk that no longer
  //           exists.
  index: 109, // shell — always loaded. Under 8.2 this was 29 kB and the
  //           Datadog RUM core sat beside it in a nameless `esm` chunk;
  //           8.3 folds that core, sonner and the radix dialog/tooltip in.
  katex: 86, // math typesetting, pulled in by lesson content rendering.
  vendor: 82, // React + react-router + react-dom.
  supabase: 61, // supabase-js v2 client.
  motion: 47, // motion / motion-dom / motion-utils, pinned out of the shell.
  ChapterList: 35, // student lesson list route.
  schemas: 20, // zod schemas shared across forms.
  config: 19, // i18next config + bundled namespaces.
  ChapterView: 14, // student chapter render (DOMPurify + i18n).
};

async function gzipSizeKb(path) {
  const buf = await readFile(path);
  const gz = await gzipAsync(buf);
  return gz.byteLength / 1024;
}

/** name → largest gzip kB among files sharing that chunk name. */
async function measure(files) {
  const sizes = new Map();
  const duplicates = new Map();
  const unparsed = [];
  for (const f of files) {
    if (!f.endsWith(".js")) continue;
    const path = join(DIST, f);
    const st = await stat(path);
    if (!st.isFile()) continue;
    const prefix = chunkPrefix(f);
    if (prefix === null) {
      // Weighed, not skipped: an unreadable name hides real payload, and
      // hiding it in silence is what let the shell chunk disappear.
      unparsed.push({ file: f, actual: await gzipSizeKb(path) });
      continue;
    }
    const gz = await gzipSizeKb(path);
    const seen = sizes.get(prefix);
    if (seen === undefined) {
      sizes.set(prefix, gz);
    } else {
      sizes.set(prefix, Math.max(seen, gz));
      duplicates.set(prefix, (duplicates.get(prefix) ?? 1) + 1);
    }
  }
  return { sizes, duplicates, unparsed };
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

  const { sizes, duplicates, unparsed } = await measure(files);
  for (const [name, count] of duplicates) {
    console.warn(`warn: chunk name "${name}" matched ${count} files; asserting on the largest.`);
  }
  if (unparsed.length > 0) {
    console.warn(
      `warn: ${unparsed.length} JS file(s) yielded no chunk name: ` +
        unparsed
          .map((u) => u.file)
          .slice(0, 5)
          .join(", ") +
        (unparsed.length > 5 ? ", …" : ""),
    );
  }

  const verdict = evaluate({ sizes, budgets: BUDGETS_GZIP_KB, unparsed });

  console.log("\nBundle-size sentinel (gzip kB):");
  console.log("  " + "chunk".padEnd(16) + "actual".padStart(10) + "  /  " + "budget".padEnd(10));
  for (const c of [...verdict.checked].sort((a, b) => b.actual - a.actual)) {
    const flag = c.actual > c.budget ? " ✗ over" : c.actual < c.budget * 0.6 ? " ✗ stale" : "";
    console.log(
      "  " +
        c.name.padEnd(16) +
        c.actual.toFixed(1).padStart(10) +
        "  /  " +
        String(c.budget).padEnd(10) +
        flag,
    );
  }
  const budgetedTotal = verdict.checked.reduce((n, c) => n + c.actual, 0);
  const allTotal = [...sizes.values()].reduce((n, v) => n + v, 0);
  console.log(
    `  ${String(sizes.size).padStart(3)} chunks total, ${verdict.checked.length} budgeted ` +
      `(${budgetedTotal.toFixed(0)} of ${allTotal.toFixed(0)} kB gzip); ` +
      `anything ≥ ${UNBUDGETED_LIMIT_KB} kB must be budgeted.`,
  );

  if (!verdict.ok) {
    console.error("\nFAIL — bundle sentinel:\n");
    for (const line of explain(verdict)) console.error("  " + line);
    console.error("");
    process.exitCode = 1;
    return;
  }
  console.log("\nOK — every chunk within budget, every budget still gating.\n");
}

main().catch((err) => {
  console.error("Unexpected sentinel error:", err);
  process.exitCode = 1;
});
