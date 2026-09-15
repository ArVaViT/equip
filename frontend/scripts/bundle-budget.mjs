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
 * 5. Did a heavy file fail to yield a chunk name at all?  (added 2026-09-14:
 *    a filename the parser cannot read used to be skipped in silence, which
 *    is how the shell chunk went missing and the build failed at random)
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
 * Length of the hash Vite appends to a chunk filename. Rolldown emits
 * base64url, so a hash is 8 characters of `[A-Za-z0-9_-]` — HYPHEN INCLUDED.
 */
export const HASH_LENGTH = 8;

/**
 * Vite chunk filenames look like `<name>-<hash>.js`. Both halves may contain
 * a hyphen — the name (`use-reduced-motion-CXFKzUjI.js`) and, about 10% of
 * the time, the base64url hash itself (`index-4HQpI-e4.js`). So the split
 * cannot be "last hyphen": it has to be "the last HASH_LENGTH characters".
 *
 * Splitting on the last hyphen is what broke production on 2026-09-14. It
 * read `index-4HQpI-e4.js` as name `index-4HQpI` + hash `e4`, rejected the
 * too-short hash, and dropped the file — so the shell chunk vanished from
 * the measurement and `index` was reported DEAD. The build then failed at
 * random, because whether a hash contains a hyphen changes with every
 * dependency bump. 20 of 204 files were misread that day.
 *
 * Returns null for anything that is not a hashed JS chunk.
 */
export function chunkPrefix(filename) {
  if (!filename.endsWith(".js")) return null;
  const stem = filename.slice(0, -3);
  const match = new RegExp(`^(.+)-([A-Za-z0-9_-]{${HASH_LENGTH}})$`).exec(stem);
  return match === null ? null : match[1];
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
 * @param {Array<{file: string, actual: number}>} [args.unparsed] JS files whose
 *   name did not yield a chunk name. A heavy one means the sentinel is blind
 *   to real payload — see question 5.
 * @param {object} [args.options] overrides for the three thresholds.
 * @returns {{over: Array, stale: Array, dead: Array, unbudgeted: Array, unreadable: Array, checked: Array, ok: boolean}}
 */
export function evaluate({ sizes, budgets, unparsed = [], options = {} }) {
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

  const unreadable = unparsed.filter((u) => u.actual >= unbudgetedLimitKb);

  over.sort((a, b) => b.actual - a.actual);
  stale.sort((a, b) => b.budget - a.budget);
  unbudgeted.sort((a, b) => b.actual - a.actual);
  dead.sort((a, b) => a.name.localeCompare(b.name));
  unreadable.sort((a, b) => b.actual - a.actual);

  return {
    over,
    stale,
    dead,
    unbudgeted,
    unreadable,
    checked,
    ok:
      over.length === 0 &&
      stale.length === 0 &&
      dead.length === 0 &&
      unbudgeted.length === 0 &&
      unreadable.length === 0,
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
  for (const v of verdict.unreadable ?? []) {
    lines.push(
      `UNREADABLE   ${v.file}: ${v.actual.toFixed(1)} kB, but the filename yields no ` +
        `chunk name, so nothing measured it. The build tool changed its hash format — ` +
        `update HASH_LENGTH / chunkPrefix to match before trusting this report.`,
    );
  }
  return lines;
}
