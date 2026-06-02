/**
 * Sentinel for ADR-0011 Wave 7 (initial slice) — editor toolbar +
 * dropdowns migrated to v2 semantic vocabulary.
 *
 * Wave 7 in the ADR is "Rich text + media" — the TipTap editor
 * surface, BlockRenderer, Callout, table styling, code-block
 * highlighting. This first slice covers the four contained
 * components (EditorToolbar, CalloutDropdown, CodeBlockDropdown,
 * TableDropdown) that share the toolbar-button + menu visual
 * vocabulary. BlockRenderer (in pages/Course/ChapterView) and the
 * lower-level prose styling (index.css table + code styling) ship
 * in a follow-up.
 */
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const COMPONENT = (...parts: string[]) =>
  resolve(HERE, "..", "..", "components", "editor", ...parts);

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

describe("ADR-0011 Wave 7 — editor toolbar slice", () => {
  it("EditorToolbar uses v2 brand + heritage + ink + edge + surface classes", () => {
    const code = readNonComment(COMPONENT("EditorToolbar.tsx"));
    expect(code.includes("ring-brand")).toBe(true);
    expect(code.includes("bg-brand/20")).toBe(true);
    expect(code.includes("text-brand")).toBe(true);
    expect(code.includes("hover:bg-heritage")).toBe(true);
    expect(code.includes("hover:text-ink")).toBe(true);
    expect(code.includes("text-ink-muted")).toBe(true);
    expect(code.includes("border-edge-strong")).toBe(true);
    expect(code.includes("bg-surface")).toBe(true);
    expect(code.includes("bg-edge")).toBe(true);
    // v1 names retired
    expect(containsClass(code, "ring-ring")).toBe(false);
    expect(containsClass(code, "bg-primary")).toBe(false);
    expect(containsClass(code, "text-primary")).toBe(false);
    expect(containsClass(code, "text-muted-foreground")).toBe(false);
    expect(containsClass(code, "hover:bg-accent")).toBe(false);
    expect(containsClass(code, "hover:text-accent-foreground")).toBe(false);
    expect(containsClass(code, "border-input")).toBe(false);
    expect(containsClass(code, "bg-background")).toBe(false);
    expect(containsClass(code, "bg-border")).toBe(false);
  });

  it("CalloutDropdown / CodeBlockDropdown / TableDropdown share v2 vocabulary", () => {
    for (const file of ["CalloutDropdown.tsx", "CodeBlockDropdown.tsx", "TableDropdown.tsx"]) {
      const code = readNonComment(COMPONENT(file));
      expect(code.includes("ring-brand"), `${file} missing ring-brand`).toBe(true);
      expect(code.includes("bg-brand/20"), `${file} missing bg-brand/20`).toBe(true);
      expect(code.includes("bg-surface-elevated"), `${file} missing bg-surface-elevated`).toBe(true);
      expect(code.includes("hover:bg-heritage"), `${file} missing hover:bg-heritage`).toBe(true);
      // v1 names retired
      expect(containsClass(code, "ring-ring"), `${file} still has ring-ring`).toBe(false);
      expect(containsClass(code, "bg-primary"), `${file} still has bg-primary`).toBe(false);
      expect(containsClass(code, "bg-background"), `${file} still has bg-background`).toBe(false);
      expect(containsClass(code, "hover:bg-muted"), `${file} still has hover:bg-muted`).toBe(false);
      expect(containsClass(code, "focus-visible:bg-muted"), `${file} still has focus-visible:bg-muted`).toBe(false);
    }
  });
});
