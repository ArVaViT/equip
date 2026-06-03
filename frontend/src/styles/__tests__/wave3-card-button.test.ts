/**
 * Sentinel for ADR-0011 Wave 3.
 *
 * Pins that Card and Button source files have been migrated to the
 * v2 semantic vocabulary. The visual snapshot can stay identical
 * because tokens-bridge.css resolves the v2 names to the same v1
 * HSL values; this sentinel is the regression net for a refactor
 * that accidentally reverts a class to the v1 name.
 *
 * Retrofitted to use the word-boundary ``containsClass`` lock-out
 * (mirrors Waves 5/6). The original `code.includes("bg-primary ")`
 * shape missed suffixed forms like `bg-primary/90` and
 * `hover:bg-accent/40` — a real risk the audit on 2026-06-02 caught.
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

describe("ADR-0011 Wave 3 — Card + Button migration", () => {
  it("tailwind.config exposes the v2 palette (surface, ink, edge, brand, heritage)", () => {
    const cfg = readFileSync(TW_CONFIG, "utf-8");
    for (const name of ["surface", "ink", "edge", "brand", "heritage"]) {
      expect(cfg.includes(name), `tailwind.config missing ${name}`).toBe(true);
    }
  });

  it("Card uses v2 classes (bg-surface-elevated / text-ink) — no resting border by default", () => {
    // 2026-06-02 UX call (Vadym): Card dropped its resting
    // ``border border-edge``; the bg-surface-elevated tone alone
    // separates the card from the page. Call sites that want a
    // frame opt back in explicitly.
    const code = readNonComment(CARD_FILE);
    expect(code.includes("bg-surface-elevated")).toBe(true);
    expect(code.includes("text-ink")).toBe(true);
    expect(code.includes("text-ink-muted")).toBe(true);
    // v1 names removed (word-boundary lock-out so suffix forms like
    // `bg-card/40` are also caught).
    expect(containsClass(code, "bg-card")).toBe(false);
    expect(containsClass(code, "text-card-foreground")).toBe(false);
    expect(containsClass(code, "border-border")).toBe(false);
    expect(containsClass(code, "text-muted-foreground")).toBe(false);
  });

  it("Button variants use v2 brand / heritage / edge / surface names", () => {
    const code = readNonComment(BUTTON_VARIANTS_FILE);
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
    expect(containsClass(code, "bg-primary")).toBe(false);
    expect(containsClass(code, "text-primary-foreground")).toBe(false);
    expect(containsClass(code, "border-input")).toBe(false);
    expect(containsClass(code, "bg-background")).toBe(false);
    expect(containsClass(code, "hover:bg-accent")).toBe(false);
    // Background + accent in any prefix form (hover:bg-accent/40 etc.)
    expect(containsClass(code, "bg-accent")).toBe(false);
  });
});
