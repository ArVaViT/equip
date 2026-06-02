/**
 * Sentinel for ADR-0011 Wave 3.
 *
 * Pins that Card and Button source files have been migrated to the
 * v2 semantic vocabulary. The visual snapshot can stay identical
 * because tokens-bridge.css resolves the v2 names to the same v1
 * HSL values; this sentinel is the regression net for a refactor
 * that accidentally reverts a class to the v1 name.
 *
 * NOT a visual diff — that's the human reviewer's job per the ADR's
 * per-wave gate ("light + dark screenshots in PR body"). This is just
 * the "did we actually do the swap" check.
 */
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const CARD_FILE = resolve(HERE, "..", "..", "components", "ui", "card.tsx");
const BUTTON_VARIANTS_FILE = resolve(
  HERE,
  "..",
  "..",
  "components",
  "ui",
  "buttonVariants.ts",
);
const TW_CONFIG = resolve(HERE, "..", "..", "..", "tailwind.config.js");

describe("ADR-0011 Wave 3 — Card + Button migration", () => {
  it("tailwind.config exposes the v2 palette (surface, ink, edge, brand, heritage)", () => {
    const cfg = readFileSync(TW_CONFIG, "utf-8");
    for (const name of ["surface", "ink", "edge", "brand", "heritage"]) {
      expect(cfg.includes(name), `tailwind.config missing ${name}`).toBe(true);
    }
  });

  it("Card uses v2 classes (bg-surface-elevated / border-edge / text-ink)", () => {
    const raw = readFileSync(CARD_FILE, "utf-8");
    // Strip comments before lock-out checks — the migration log
    // mentions the v1 names in a comment we want to keep.
    const code = raw.replace(/\/\/[^\n]*\n/g, "\n").replace(/\/\*[\s\S]*?\*\//g, "");
    expect(code.includes("bg-surface-elevated")).toBe(true);
    expect(code.includes("border-edge")).toBe(true);
    expect(code.includes("text-ink")).toBe(true);
    expect(code.includes("text-ink-muted")).toBe(true);
    // v1 names removed from the Card source (they would silently
    // resolve to the same colors, so we lock them out by class name).
    expect(code.includes("bg-card")).toBe(false);
    expect(code.includes("text-card-foreground")).toBe(false);
    expect(code.includes("border-border")).toBe(false);
    expect(code.includes("text-muted-foreground")).toBe(false);
  });

  it("Button variants use v2 brand / heritage / edge / surface names", () => {
    const raw = readFileSync(BUTTON_VARIANTS_FILE, "utf-8");
    const code = raw.replace(/\/\/[^\n]*\n/g, "\n").replace(/\/\*[\s\S]*?\*\//g, "");
    // Primary CTA = brand.
    expect(code.includes("bg-brand text-brand-foreground")).toBe(true);
    expect(code.includes("bg-brand-quiet")).toBe(true);
    // Outline / ghost surface vocabulary.
    expect(code.includes("bg-surface")).toBe(true);
    expect(code.includes("border-edge-strong")).toBe(true);
    expect(code.includes("hover:bg-heritage")).toBe(true);
    // Link uses brand for the text color.
    expect(code.includes("text-brand")).toBe(true);
    // Old v1 names retired from the variants (disabled stays muted —
    // that's wave 4's surface and intentionally still v1 here).
    expect(code.includes("bg-primary ")).toBe(false);
    expect(code.includes("text-primary-foreground")).toBe(false);
    expect(code.includes("border-input")).toBe(false);
    expect(code.includes("bg-background")).toBe(false);
    expect(code.includes("hover:bg-accent ")).toBe(false);
  });
});
