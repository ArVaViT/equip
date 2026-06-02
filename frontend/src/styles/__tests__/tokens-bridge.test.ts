/**
 * Sentinel for the Wave 2 bridge layer.
 *
 * Pins:
 * - Bridge file exists, parses, and is imported by index.css (Wave 2
 *   IS wired, unlike Wave 1 which was preview-only).
 * - Every token name from tokens-v2.css ALSO appears in the bridge
 *   so any component using a v2 name has a backing value today.
 * - Every bridge value is a ``var(--*)`` pass-through into the v1
 *   palette (no direct hex / hsl / oklch — those belong in the
 *   palette files, not the bridge).
 */
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const BRIDGE_FILE = resolve(HERE, "..", "tokens-bridge.css");
const V2_FILE = resolve(HERE, "..", "tokens-v2.css");
const INDEX_FILE = resolve(HERE, "..", "..", "index.css");

const REQUIRED_TOKENS = [
  "--color-surface",
  "--color-surface-elevated",
  "--color-surface-sunken",
  "--color-ink",
  "--color-ink-muted",
  "--color-ink-inverted",
  "--color-accent",
  "--color-accent-quiet",
  "--color-accent-strong",
  "--color-heritage",
  "--color-heritage-quiet",
  "--color-edge",
  "--color-edge-strong",
  "--color-success",
  "--color-success-quiet",
  "--color-warning",
  "--color-warning-quiet",
  "--color-danger",
  "--color-danger-quiet",
  "--color-info",
  "--color-info-quiet",
  "--color-focus-ring",
];

describe("tokens-bridge.css (ADR-0011 Wave 2)", () => {
  it("file is present + readable", () => {
    const content = readFileSync(BRIDGE_FILE, "utf-8");
    expect(content.length).toBeGreaterThan(200);
  });

  it("is imported by index.css (Wave 2 IS wired)", () => {
    const index = readFileSync(INDEX_FILE, "utf-8");
    expect(index.includes("tokens-bridge")).toBe(true);
  });

  it("matches the canonical v2 token vocabulary", () => {
    const bridge = readFileSync(BRIDGE_FILE, "utf-8");
    const v2 = readFileSync(V2_FILE, "utf-8");
    for (const token of REQUIRED_TOKENS) {
      // Both files must declare every canonical token name.
      expect(bridge.includes(token), `bridge missing ${token}`).toBe(true);
      expect(v2.includes(token), `tokens-v2 missing ${token}`).toBe(true);
    }
  });

  it("declares every token in both :root and .dark scopes", () => {
    const bridge = readFileSync(BRIDGE_FILE, "utf-8");
    const [light = "", dark = ""] = bridge.split(".dark");
    for (const token of REQUIRED_TOKENS) {
      expect(light.includes(token), `:root missing ${token}`).toBe(true);
      expect(dark.includes(token), `.dark missing ${token}`).toBe(true);
    }
  });

  it("uses only var(--*) pass-throughs (no hex / hsl / oklch literals)", () => {
    const bridge = readFileSync(BRIDGE_FILE, "utf-8");
    // Strip comments first so the ADR reference + explanation prose
    // doesn't trigger the hex / hsl matchers.
    const stripped = bridge.replace(/\/\*[\s\S]*?\*\//g, "");
    expect(stripped.match(/#[0-9a-fA-F]{3,8}/g) ?? []).toEqual([]);
    expect(stripped.match(/hsl\s*\(/g) ?? []).toEqual([]);
    expect(stripped.match(/oklch\s*\(/g) ?? []).toEqual([]);
  });
});
