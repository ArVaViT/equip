/**
 * Sentinel for ADR-0011 Wave 4 — form primitives migration.
 *
 * Asserts that Label, Input (via inputVariants), and Checkbox have
 * been swapped to the v2 semantic vocabulary. Pixels stay identical
 * via the tokens-bridge layer; this sentinel just locks the swap in
 * source.
 */
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const COMPONENT = (...parts: string[]) =>
  resolve(HERE, "..", "..", "components", "ui", ...parts);

function readNonComment(path: string): string {
  const raw = readFileSync(path, "utf-8");
  return raw.replace(/\/\/[^\n]*\n/g, "\n").replace(/\/\*[\s\S]*?\*\//g, "");
}

describe("ADR-0011 Wave 4 — form primitives migration", () => {
  it("Label uses text-ink (v2) instead of text-foreground (v1)", () => {
    const code = readNonComment(COMPONENT("label.tsx"));
    expect(code.includes("text-ink")).toBe(true);
    expect(code.includes("text-foreground")).toBe(false);
  });

  it("Input variants use v2 surface / edge / ink-muted / brand classes", () => {
    const code = readNonComment(COMPONENT("inputVariants.ts"));
    expect(code.includes("border-edge-strong")).toBe(true);
    expect(code.includes("bg-surface")).toBe(true);
    expect(code.includes("text-ink-muted")).toBe(true);
    expect(code.includes("ring-brand")).toBe(true);
    // v1 names retired from the source (still appear in the migration
    // comment, but readNonComment strips those out).
    expect(code.includes("border-input")).toBe(false);
    expect(code.includes("bg-background")).toBe(false);
    expect(code.includes("text-muted-foreground")).toBe(false);
    // ``ring-ring`` is the v1 focus ring — check no spaced/non-comment
    // usage remains.
    expect(code.includes("ring-ring")).toBe(false);
  });

  it("Checkbox uses v2 brand / surface / edge classes", () => {
    const code = readNonComment(COMPONENT("checkbox.tsx"));
    expect(code.includes("border-edge-strong")).toBe(true);
    expect(code.includes("bg-surface")).toBe(true);
    expect(code.includes("data-[state=checked]:bg-brand")).toBe(true);
    expect(code.includes("data-[state=checked]:text-brand-foreground")).toBe(true);
    expect(code.includes("focus-visible:ring-brand")).toBe(true);
    // v1 names retired from source.
    expect(code.includes("border-input")).toBe(false);
    expect(code.includes("bg-background")).toBe(false);
    expect(code.includes("bg-primary")).toBe(false);
    expect(code.includes("text-primary-foreground")).toBe(false);
  });
});
