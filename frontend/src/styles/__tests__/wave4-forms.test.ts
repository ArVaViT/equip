/**
 * Sentinel for ADR-0011 Wave 4 — form primitives migration.
 *
 * Asserts that Label, Input (via inputVariants), and Checkbox have
 * been swapped to the v2 semantic vocabulary. Pixels stay identical
 * via the tokens-bridge layer; this sentinel just locks the swap in
 * source.
 *
 * Retrofitted to use the word-boundary ``containsClass`` helper so
 * suffixed forms (`bg-primary/90`, `hover:bg-accent/40`) also count
 * as v1 leakage. The original substring lock-out missed those.
 */
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const COMPONENT = (...parts: string[]) =>
  resolve(HERE, "..", "..", "components", "ui", ...parts);

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

describe("ADR-0011 Wave 4 — form primitives migration", () => {
  it("Label uses text-ink (v2) instead of text-foreground (v1)", () => {
    const code = readNonComment(COMPONENT("label.tsx"));
    expect(code.includes("text-ink")).toBe(true);
    expect(containsClass(code, "text-foreground")).toBe(false);
  });

  it("Input variants use v2 surface / edge / ink-muted / brand classes", () => {
    const code = readNonComment(COMPONENT("inputVariants.ts"));
    expect(code.includes("border-edge-strong")).toBe(true);
    expect(code.includes("bg-surface")).toBe(true);
    expect(code.includes("text-ink-muted")).toBe(true);
    expect(code.includes("ring-brand")).toBe(true);
    // v1 names retired (word-boundary so `bg-background/40` etc.
    // are also caught).
    expect(containsClass(code, "border-input")).toBe(false);
    expect(containsClass(code, "bg-background")).toBe(false);
    expect(containsClass(code, "text-muted-foreground")).toBe(false);
    expect(containsClass(code, "ring-ring")).toBe(false);
  });

  it("Checkbox uses v2 brand / surface / edge classes", () => {
    const code = readNonComment(COMPONENT("checkbox.tsx"));
    expect(code.includes("border-edge-strong")).toBe(true);
    expect(code.includes("bg-surface")).toBe(true);
    expect(code.includes("data-[state=checked]:bg-brand")).toBe(true);
    expect(code.includes("data-[state=checked]:text-brand-foreground")).toBe(true);
    expect(code.includes("focus-visible:ring-brand")).toBe(true);
    // v1 names retired from source.
    expect(containsClass(code, "border-input")).toBe(false);
    expect(containsClass(code, "bg-background")).toBe(false);
    expect(containsClass(code, "bg-primary")).toBe(false);
    expect(containsClass(code, "text-primary-foreground")).toBe(false);
  });
});
