/**
 * Sentinel for ADR-0011 Wave 5 — Surfaces migration.
 *
 * Locks Modal (dialog.tsx), AlertDialog, Sheet, Popover, and Tooltip
 * onto the v2 semantic vocabulary. Pixels are identical via the
 * tokens-bridge today. Each lock-out below uses `\b` word boundary
 * regex (Wave 3 used a brittle substring check that missed
 * `bg-primary/90` and `hover:bg-accent/40`; that lesson is applied
 * here).
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
  return raw
    .replace(/\/\/[^\n]*\n/g, "\n")
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/\{\/\*[\s\S]*?\*\/\}/g, "");
}

/** Stronger lock-out: matches the class name regardless of suffix
 *  (`/90`, `/40`, `:hover`, etc.). The v1 class name appearing
 *  anywhere as a Tailwind class is a regression we want to catch. */
function containsClass(code: string, className: string): boolean {
  const escaped = className.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const re = new RegExp(`\\b${escaped}\\b`);
  return re.test(code);
}

describe("ADR-0011 Wave 5 — Surfaces migration", () => {
  it("popover uses v2 surface-elevated + edge + ink", () => {
    const code = readNonComment(COMPONENT("popover.tsx"));
    expect(code.includes("bg-surface-elevated")).toBe(true);
    expect(code.includes("border-edge")).toBe(true);
    expect(code.includes("text-ink")).toBe(true);
    expect(containsClass(code, "bg-popover")).toBe(false);
    expect(containsClass(code, "text-popover-foreground")).toBe(false);
    expect(containsClass(code, "border-border")).toBe(false);
  });

  it("tooltip uses bg-brand (matches primary, not ink)", () => {
    const code = readNonComment(COMPONENT("tooltip.tsx"));
    expect(code.includes("bg-brand")).toBe(true);
    expect(code.includes("text-brand-foreground")).toBe(true);
    expect(containsClass(code, "bg-primary")).toBe(false);
    expect(containsClass(code, "text-primary-foreground")).toBe(false);
  });

  it("dialog uses v2 surface + brand-ring + heritage open-state", () => {
    const code = readNonComment(COMPONENT("dialog.tsx"));
    expect(code.includes("bg-surface")).toBe(true);
    expect(code.includes("focus-visible:ring-brand")).toBe(true);
    expect(code.includes("data-[state=open]:bg-heritage")).toBe(true);
    expect(code.includes("data-[state=open]:text-ink-muted")).toBe(true);
    expect(containsClass(code, "bg-background")).toBe(false);
    expect(containsClass(code, "ring-ring")).toBe(false);
    expect(containsClass(code, "bg-accent")).toBe(false);
    expect(containsClass(code, "text-muted-foreground")).toBe(false);
  });

  it("sheet uses v2 surface + edge + ink + brand-ring", () => {
    const code = readNonComment(COMPONENT("sheet.tsx"));
    expect(code.includes("bg-surface")).toBe(true);
    expect(code.includes("border-edge")).toBe(true);
    expect(code.includes("text-ink")).toBe(true);
    expect(code.includes("text-ink-muted")).toBe(true);
    expect(code.includes("focus-visible:ring-brand")).toBe(true);
    expect(containsClass(code, "bg-background")).toBe(false);
    expect(containsClass(code, "border-border")).toBe(false);
    expect(containsClass(code, "text-foreground")).toBe(false);
    expect(containsClass(code, "text-muted-foreground")).toBe(false);
    expect(containsClass(code, "ring-ring")).toBe(false);
  });

  it("alert-dialog uses v2 edge + surface + ink classes", () => {
    const code = readNonComment(COMPONENT("alert-dialog.tsx"));
    expect(code.includes("border-edge")).toBe(true);
    expect(code.includes("bg-surface")).toBe(true);
    expect(code.includes("text-ink")).toBe(true);
    expect(code.includes("text-ink-muted")).toBe(true);
    expect(code.includes("bg-ink-muted")).toBe(true);
    expect(code.includes("focus-visible:ring-brand")).toBe(true);
    expect(containsClass(code, "border-border")).toBe(false);
    expect(containsClass(code, "border-input")).toBe(false);
    expect(containsClass(code, "bg-background")).toBe(false);
    expect(containsClass(code, "text-foreground")).toBe(false);
    expect(containsClass(code, "text-muted-foreground")).toBe(false);
    expect(containsClass(code, "bg-muted-foreground")).toBe(false);
    expect(containsClass(code, "ring-ring")).toBe(false);
  });
});
