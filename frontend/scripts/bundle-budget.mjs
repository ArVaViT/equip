/*
 * Pure logic behind the bundle-size sentinel. No filesystem, no process
 * exit — `check-bundle-size.mjs` does the IO and this decides the verdict,
 * so the rules can be unit-tested instead of trusted.
 *
 * The sentinel answers four questions, not one. Only the first was ever
 * asked before 2026-09-13, and on that date the other three all had bad
 * answers in main:
 *
 * 1. Did a budgeted chunk grow past its ceiling?  (regression)
 * 2. Is a chunk far enough under its ceiling that the ceiling no longer
 *    gates anything?  (`index` sat at 24.5 kB under a 200 kB budget — it
 *    could have grown eightfold in silence)
 * 3. Does a budget name still match an emitted chunk?  (`dnd.esm` had a
 *    35 kB budget and no chunk; the rename went unnoticed)
 * 4. Is a heavy chunk missing from the budget table entirely?  (7 of 178
 *    chunks were budgeted; `katex` at 74.7 kB — heavier than `vendor` —
 *    was not one of them)
 */

/** Budget is treated as stale when actual < budget * this. */
export const STALE_RATIO = 0.6;

/**
 * Chunks smaller than this skip the staleness check. A 3 kB chunk under a
 * 6 kB budget is noise, not drift, and failing on it would make the gate
 * something people disable.
 */
export const MIN_STALE_KB = 10;

/** A chunk at least this large must carry an explicit budget. */
export const UNBUDGETED_LIMIT_KB = 25;

/**
 * Vite chunk filenames look like `<name>-<hash>.js`. The name can contain
 * dots (`dnd.esm-DcITUONc.js`), so split on the LAST hyphen and treat what
 * precedes it as the chunk name. Returns null for anything that is not a
 * hashed JS chunk.
 */
export function chunkPrefix(filename) {
  if (!filename.endsWith(".js")) return null;
  const stem = filename.slice(0, -3);
  const lastDash = stem.lastIndexOf("-");
  if (lastDash <= 0) return null;
  const name = stem.slice(0, lastDash);
  const hash = stem.slice(lastDash + 1);
  if (!/^[A-Za-z0-9_-]{6,}$/.test(hash)) return null;
  return name;
}

/**
 * Decide the verdict.
 *
 * @param {object} args
 * @param {Map<string, number>|Record<string, number>} args.sizes
 *   chunk name → gzip kB. When several files share a name the caller
 *   passes the largest: that is the real payload, and a same-named import
 *   facade would otherwise shadow it.
 * @param {Record<string, number>} args.budgets chunk name → gzip kB ceiling.
 * @param {object} [args.options] overrides for the three thresholds.
 * @returns {{over: Array, stale: Array, dead: Array, unbudgeted: Array, checked: Array, ok: boolean}}
 */
export function evaluate({ sizes, budgets, options = {} }) {
  const staleRatio = options.staleRatio ?? STALE_RATIO;
  const minStaleKb = options.minStaleKb ?? MIN_STALE_KB;
  const unbudgetedLimitKb = options.unbudgetedLimitKb ?? UNBUDGETED_LIMIT_KB;

  const sizeMap = sizes instanceof Map ? sizes : new Map(Object.entries(sizes));

  const over = [];
  const stale = [];
  const dead = [];
  const unbudgeted = [];
  const checked = [];

  for (const [name, budget] of Object.entries(budgets)) {
    const actual = sizeMap.get(name);
    if (actual === undefined) {
      dead.push({ name, budget });
      continue;
    }
    checked.push({ name, actual, budget });
    if (actual > budget) {
      over.push({ name, actual, budget });
    } else if (actual >= minStaleKb && actual < budget * staleRatio) {
      stale.push({ name, actual, budget, suggested: Math.ceil(actual * 1.15) });
    }
  }

  for (const [name, actual] of sizeMap) {
    if (name in budgets) continue;
    if (actual >= unbudgetedLimitKb) {
      unbudgeted.push({ name, actual, suggested: Math.ceil(actual * 1.15) });
    }
  }

  over.sort((a, b) => b.actual - a.actual);
  stale.sort((a, b) => b.budget - a.budget);
  unbudgeted.sort((a, b) => b.actual - a.actual);
  dead.sort((a, b) => a.name.localeCompare(b.name));

  return {
    over,
    stale,
    dead,
    unbudgeted,
    checked,
    ok: over.length === 0 && stale.length === 0 && dead.length === 0 && unbudgeted.length === 0,
  };
}

/** Human-readable reasons for a failing verdict, one line each. */
export function explain(verdict) {
  const lines = [];
  for (const v of verdict.over) {
    lines.push(
      `OVER BUDGET  ${v.name}: ${v.actual.toFixed(1)} kB > ${v.budget} kB. ` +
        `Something heavy landed in this chunk. If the growth is intentional, ` +
        `raise the budget in the same PR and say why in the commit message.`,
    );
  }
  for (const v of verdict.stale) {
    lines.push(
      `STALE BUDGET ${v.name}: ${v.actual.toFixed(1)} kB against a ${v.budget} kB ceiling — ` +
        `the budget stopped gating. Lower it to ~${v.suggested} kB.`,
    );
  }
  for (const v of verdict.dead) {
    lines.push(
      `DEAD BUDGET  ${v.name}: budgeted at ${v.budget} kB but no such chunk is emitted. ` +
        `The chunk was renamed or removed — drop the entry or point it at the new name.`,
    );
  }
  for (const v of verdict.unbudgeted) {
    lines.push(
      `NO BUDGET    ${v.name}: ${v.actual.toFixed(1)} kB and nothing is watching it. ` +
        `Add an entry (~${v.suggested} kB) or split the chunk.`,
    );
  }
  return lines;
}
