/**
 * Sentinel for ADR-0011 Wave 7 follow-up — block-editor surface
 * migrated to v2.
 *
 * Covers the remaining editor files that the first Wave 7 PR (#670)
 * left for later: RichTextEditor, ChapterBlockEditor, blocks/BlockRow,
 * blocks/TextBlockEditor, blocks/FileBlockEditor, blocks/AddBlockMenu.
 *
 * Note: ``bg-muted`` / ``hover:bg-muted`` stay on v1 in some places
 * because the v2 vocabulary doesn't expose a ``muted`` alias in
 * tailwind.config yet (deferred to a later wave). The locks below
 * only check the migrated tokens.
 */
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));

function rel(...parts: string[]): string {
  return resolve(HERE, "..", "..", "components", "editor", ...parts);
}

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

const FILES = [
  rel("RichTextEditor.tsx"),
  rel("ChapterBlockEditor.tsx"),
  rel("blocks", "BlockRow.tsx"),
  rel("blocks", "TextBlockEditor.tsx"),
  rel("blocks", "FileBlockEditor.tsx"),
  rel("blocks", "AddBlockMenu.tsx"),
];

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

describe("ADR-0011 Wave 7 follow-up — block editor surface migration", () => {
  for (const path of FILES) {
    const name = path.split(/[\\/]/).slice(-1)[0];

    it(`${name} retired the v1 names`, () => {
      const code = readNonComment(path);
      for (const cls of V1_LOCKED_OUT) {
        expect(
          containsClass(code, cls),
          `${name} still references ${cls}`,
        ).toBe(false);
      }
    });
  }
});
