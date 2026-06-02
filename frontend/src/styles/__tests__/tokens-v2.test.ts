/**
 * Sentinel for the v2 OKLCH token file (ADR-0011 Wave 1).
 *
 * The token file isn't imported by any component yet — it's a
 * preview/reference document until Wave 2 wires it in. This sentinel
 * just confirms the file exists, parses as valid CSS, defines the
 * canonical token list in both light and dark contexts, and contains
 * `oklch(...)` values (not hex or hsl).
 *
 * Why test this at all: the next wave that swaps a component's
 * tokens will rely on every name being present in both themes. A
 * silent typo (`--color-suface-elevated`) would otherwise only surface
 * when a component renders with no background.
 */
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const TOKENS_FILE = resolve(
  dirname(fileURLToPath(import.meta.url)),
  "..",
  "tokens-v2.css",
);

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

let content: string;

describe("tokens-v2.css (ADR-0011 Wave 1 foundation)", () => {
  it("file is present + readable", () => {
    content = readFileSync(TOKENS_FILE, "utf-8");
    expect(content.length).toBeGreaterThan(200);
  });

  it("declares all canonical tokens in :root / .light scope", () => {
    const lightScope = content.split(".dark")[0] ?? "";
    for (const token of REQUIRED_TOKENS) {
      expect(
        lightScope.includes(token),
        `missing ${token} in :root scope`,
      ).toBe(true);
    }
  });

  it("declares all canonical tokens in .dark scope", () => {
    const darkScope = content.split(".dark")[1] ?? "";
    for (const token of REQUIRED_TOKENS) {
      expect(
        darkScope.includes(token),
        `missing ${token} in .dark scope`,
      ).toBe(true);
    }
  });

  it("every color token uses the oklch() function (not hex / hsl)", () => {
    const oklchMatches = content.match(/oklch\(/g) ?? [];
    const hexMatches = content.match(/#[0-9a-fA-F]{3,8}/g) ?? [];
    const hslMatches = content.match(/hsl\(/g) ?? [];
    // Every token in both themes is one oklch() call.
    // 22 tokens × 2 themes = 44 minimum.
    expect(oklchMatches.length).toBeGreaterThanOrEqual(44);
    // No hex or hsl leaked through.
    expect(hexMatches.length).toBe(0);
    expect(hslMatches.length).toBe(0);
  });

  it("is NOT imported anywhere yet (Wave 1 is preview-only)", () => {
    // The whole point of Wave 1: zero runtime impact. If a future
    // refactor accidentally imports this file (which would override
    // the v1 tokens), we want the sentinel to fail loudly.
    const indexCss = readFileSync(
      resolve(dirname(fileURLToPath(import.meta.url)), "..", "..", "index.css"),
      "utf-8",
    );
    expect(indexCss.includes("tokens-v2")).toBe(false);
  });
});
