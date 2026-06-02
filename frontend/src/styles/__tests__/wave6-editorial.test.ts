/**
 * Sentinel for ADR-0011 Wave 6 — Editorial primitives migration.
 *
 * Locks Badge, EmptyState, ErrorState, PageHeader, StatCard onto the
 * v2 semantic vocabulary. Uses the word-boundary `containsClass`
 * helper from Wave 5 to avoid the brittle substring lock-out that
 * Wave 3's sentinel had.
 *
 * Notable: success / warning / info / destructive / muted variants
 * stay on v1 because the bridge doesn't (yet) expose v2 aliases for
 * those semantic tones in tailwind.config.js. Locks here only
 * assert the migrated portion.
 */
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const COMPONENT_UI = (...parts: string[]) =>
  resolve(HERE, "..", "..", "components", "ui", ...parts);
const COMPONENT_PATTERN = (...parts: string[]) =>
  resolve(HERE, "..", "..", "components", "patterns", ...parts);

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

describe("ADR-0011 Wave 6 — Editorial primitives migration", () => {
  it("Badge default variant uses brand vocabulary", () => {
    const code = readNonComment(COMPONENT_UI("badge.tsx"));
    expect(code.includes("bg-brand")).toBe(true);
    expect(code.includes("text-brand-foreground")).toBe(true);
    expect(code.includes("bg-brand-quiet")).toBe(true);
    expect(code.includes("bg-heritage")).toBe(true);
    expect(code.includes("focus-visible:ring-brand")).toBe(true);
    expect(code.includes("text-ink")).toBe(true);
    // v1 names retired for the migrated variants. The v1 success/
    // warning/info/destructive/muted variants stay (no v2 aliases
    // in tailwind config yet); their classes are NOT locked out
    // here.
    expect(containsClass(code, "bg-primary")).toBe(false);
    expect(containsClass(code, "text-primary-foreground")).toBe(false);
    expect(containsClass(code, "bg-secondary")).toBe(false);
    expect(containsClass(code, "text-secondary-foreground")).toBe(false);
    expect(containsClass(code, "bg-accent")).toBe(false);
    expect(containsClass(code, "text-accent-foreground")).toBe(false);
    expect(containsClass(code, "ring-ring")).toBe(false);
    expect(containsClass(code, "text-foreground")).toBe(false);
  });

  it("EmptyState uses surface + edge + ink vocabulary", () => {
    const code = readNonComment(COMPONENT_PATTERN("EmptyState.tsx"));
    expect(code.includes("bg-surface")).toBe(true);
    expect(code.includes("border-edge")).toBe(true);
    expect(code.includes("text-ink")).toBe(true);
    expect(code.includes("text-ink-muted")).toBe(true);
    expect(containsClass(code, "bg-background")).toBe(false);
    expect(containsClass(code, "border-border")).toBe(false);
    expect(containsClass(code, "text-foreground")).toBe(false);
    expect(containsClass(code, "text-muted-foreground")).toBe(false);
  });

  it("ErrorState uses ink vocabulary", () => {
    const code = readNonComment(COMPONENT_PATTERN("ErrorState.tsx"));
    expect(code.includes("text-ink")).toBe(true);
    expect(code.includes("text-ink-muted")).toBe(true);
    expect(containsClass(code, "text-foreground")).toBe(false);
    expect(containsClass(code, "text-muted-foreground")).toBe(false);
  });

  it("PageHeader back-link uses v2 focus ring + ink-muted vocabulary", () => {
    const code = readNonComment(COMPONENT_PATTERN("PageHeader.tsx"));
    expect(code.includes("text-ink-muted")).toBe(true);
    expect(code.includes("hover:text-ink")).toBe(true);
    expect(code.includes("focus-visible:ring-brand")).toBe(true);
    expect(containsClass(code, "text-muted-foreground")).toBe(false);
    expect(containsClass(code, "ring-ring")).toBe(false);
  });

  it("StatCard uses ink-muted for labels", () => {
    const code = readNonComment(COMPONENT_PATTERN("StatCard.tsx"));
    expect(code.includes("text-ink-muted")).toBe(true);
    expect(containsClass(code, "text-muted-foreground")).toBe(false);
  });
});
