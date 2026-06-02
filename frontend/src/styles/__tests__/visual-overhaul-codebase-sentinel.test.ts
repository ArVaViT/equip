/**
 * ADR-0011 codebase-wide sentinel — every Tailwind class that
 * appears in source code is checked against the v1 lock-out list.
 *
 * Why a codebase scan instead of per-file sentinels alone?
 *
 * The per-wave sentinels (wave3 .. wave16) catch regression within
 * files that were migrated. They do NOT catch a brand-new file that
 * lands on `main` carrying v1 vocabulary — that would silently
 * re-introduce the old palette in a new corner of the surface.
 *
 * This test walks every `.tsx` / `.ts` file under `src/`, strips
 * comments, and asserts none reference the v1 tokens. Comments are
 * stripped because the per-wave files contain migration-story
 * comments (e.g., "ADR-0011 Wave 5 — text-foreground -> text-ink")
 * that document the change — those should stay, but they would
 * false-positive a literal text search.
 *
 * If you DELIBERATELY need to introduce a v1 reference (for an
 * external library wrapper, a temporary visual A/B, etc.), add the
 * file to `ALLOW` below with a comment justifying why.
 */
import { describe, it, expect } from "vitest";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { resolve, dirname, relative } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC = resolve(HERE, "..", "..");

function readNonComment(path: string): string {
  return readFileSync(path, "utf-8")
    .replace(/\/\/[^\n]*\n/g, "\n")
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/\{\/\*[\s\S]*?\*\/\}/g, "");
}

function containsClass(code: string, className: string): boolean {
  const escaped = className.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return new RegExp(`\\b${escaped}\\b`).test(code);
}

function* walk(dir: string): Generator<string> {
  for (const entry of readdirSync(dir)) {
    const path = resolve(dir, entry);
    const st = statSync(path);
    if (st.isDirectory()) {
      // Skip __tests__ folders — they intentionally reference v1
      // names to assert their absence, so a literal text scan would
      // false-positive.
      if (entry === "__tests__" || entry === "node_modules") continue;
      yield* walk(path);
    } else if (path.endsWith(".tsx") || path.endsWith(".ts")) {
      yield path;
    }
  }
}

// File-level allow-list. Add a path here ONLY if the file legitimately
// needs to keep a v1 token (e.g., wrapper for a third-party widget
// whose theme exposes a v1 name). Add a one-line comment justifying
// the exception.
const ALLOW: ReadonlySet<string> = new Set<string>([
  // ADR-0011 bridge: tokens-bridge.css is *imported* via `index.css`
  // but is itself plain CSS, not TS — wouldn't be matched anyway.
]);

const V1_LOCKED_OUT = [
  "bg-background",
  "text-foreground",
  "text-muted-foreground",
  "border-border",
  "border-input",
  "bg-primary",
  "text-primary",
  "border-primary",
  "hover:bg-accent",
  "hover:text-accent-foreground",
  "ring-ring",
  "bg-muted-foreground",
];

describe("ADR-0011 — no v1 vocabulary anywhere in src/ source code", () => {
  it("every src/*.tsx / src/*.ts (outside __tests__) is on v2", () => {
    const offenders: { file: string; cls: string }[] = [];
    for (const path of walk(SRC)) {
      // ``String.prototype.replaceAll`` needs lib >= ES2021; the project's
      // tsconfig targets a lower lib for runtime breadth. Use a regex to
      // normalize Windows path separators without needing ES2021 lib.
      const rel = relative(SRC, path).replace(/\\/g, "/");
      if (ALLOW.has(rel)) continue;
      const code = readNonComment(path);
      for (const cls of V1_LOCKED_OUT) {
        if (containsClass(code, cls)) {
          offenders.push({ file: rel, cls });
        }
      }
    }
    expect(
      offenders,
      `Found v1 token references — migrate them to v2 or allow-list:\n${offenders
        .map((o) => `  ${o.file}: ${o.cls}`)
        .join("\n")}`,
    ).toEqual([]);
  });
});
